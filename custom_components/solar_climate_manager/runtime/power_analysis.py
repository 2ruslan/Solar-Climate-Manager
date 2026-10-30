"""Read-only observation service. Its store and failures cannot authorize commands."""

import asyncio
import hashlib
import json
import logging
import sqlite3
from collections import deque
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from statistics import median
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from ..adapters.analysis_database import MAX_PAYLOAD, AnalysisDatabase
from ..adapters.sources import climate_temperature
from ..domain.power_analysis import Conditions, GroupAnalysis
from ..model import temperature_celsius

LOGGER = logging.getLogger(__name__)


class PowerAnalysis:
    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self.groups: dict[str, GroupAnalysis] = {}
        self.store: Any = None
        self.loaded = False
        self.error: str | None = None
        self.lock = asyncio.Lock()
        self.last_save = 0.0
        self.database: AnalysisDatabase | None = None
        self.pending: deque[tuple[str, str, float, float, str]] = deque(maxlen=120)
        self.sql_lock = asyncio.Lock()
        self.sql_task: asyncio.Task[None] | None = None
        self.timer_unsub: Any = None
        self.last_sql = 0.0
        self.queued_minutes: dict[str, tuple[str, int]] = {}

    async def async_load(self) -> None:
        async with self.lock:
            if self.loaded:
                return
            from homeassistant.helpers.storage import Store

            self.store = Store(self.hass, 1, "solar_climate_manager.power_analysis")
            self.database = AnalysisDatabase(self.hass.config.path(".storage", "solar_climate_manager_analysis.sqlite"))
            try:
                saved = await self.store.async_load()
                if saved is not None and (not isinstance(saved, dict) or saved.get("version") != 1):
                    raise ValueError("unsupported_analysis_store")
                groups = saved.get("groups", {}) if saved else {}
                if not isinstance(groups, dict):
                    raise ValueError("invalid_analysis_store")
                now = dt_util.utcnow().timestamp()
                self.groups = {key: GroupAnalysis.restore(data, now)
                               for key, data in list(groups.items())[:100] if isinstance(key, str)}
            except (ValueError, OSError, HomeAssistantError):
                self.error = "storage_error"
                LOGGER.exception("Power analysis storage unavailable; control is unaffected")
            self.loaded = True
            await self.async_process()

    async def async_process(self, _time: Any = None) -> None:
        async with self.sql_lock:
            if self.error or self.database is None:
                return
            batch = list(self.pending)
            self.pending.clear()
            models = {k: (v.context, deepcopy(v.adaptive)) for k, v in self.groups.items()}
            try:
                updated = await self.hass.async_add_executor_job(
                    self.database.exchange, batch, models, dt_util.utcnow().timestamp())
                for key, (context, model) in updated.items():
                    if key in self.groups and self.groups[key].context == context:
                        self.groups[key].adaptive = model
                if self.store is not None:
                    await self.store.async_save(self.stored())
            except (OSError, ValueError, sqlite3.Error, HomeAssistantError):
                self.error = "storage_error"
                LOGGER.exception("Analysis database unavailable; control is unaffected")

    def stored(self) -> dict[str, Any]:
        return {"version": 1, "groups": {k: v.stored() for k, v in self.groups.items()}}

    async def async_flush(self) -> None:
        if self.timer_unsub:
            self.timer_unsub()
            self.timer_unsub = None
        if self.sql_task:
            await self.sql_task
            self.sql_task = None
        await self.async_process()
        if self.store is not None and self.error is None:
            try:
                await self.store.async_save(self.stored())
            except (OSError, HomeAssistantError):
                self.error = "storage_error"
                LOGGER.exception("Cannot save power analysis; control is unaffected")
        for group in self.groups.values():
            group.reset_cycle()
            group.adaptive.reset("waiting_background")
            group.last_report = group.last_sample = None

    def conditions(self, coordinator: Any, *, phase: str = "steady") -> Conditions | None:
        settings = coordinator.settings
        climate = self.hass.states.get(settings["climate_entity"])
        if climate is None or climate.state in ("unknown", "unavailable"):
            return None
        mode = climate.state if climate.state != "off" else settings["hvac_mode"]
        if mode not in ("heat", "cool"):
            return None
        unit = self.hass.config.units.temperature_unit
        indoor = climate_temperature(climate, "current_temperature", unit)
        target = climate_temperature(climate, "temperature", unit)
        if indoor is None or target is None:
            return None
        outdoor = None
        if settings.get("outdoor_temperature_entity"):
            state = self.hass.states.get(settings["outdoor_temperature_entity"])
            if state and 0 <= dt_util.utcnow().timestamp() - state.last_reported.timestamp() <= 900:
                outdoor = temperature_celsius(state.state, state.attributes.get("unit_of_measurement"))
            if outdoor is None:
                return None
        fan = climate.attributes.get("fan_mode", "unknown")
        return Conditions(mode, str(fan)[:100], indoor, target, outdoor, phase)

    def observe(self, group: Any, registry: Any, devices: dict[str, Any], snapshot: Any) -> None:
        if not self.loaded or self.error:
            return
        members = sorted(m.device_id for m in registry.memberships if m.group_id == group.group_id)
        if any(key not in devices for key in members):
            if group.group_id in self.groups:
                self.groups[group.group_id].reject("invalid_data")
                self.groups[group.group_id].adaptive.reset("invalid_data")
            return
        context = [group.sources.load_power_entity, group.policy.load_scope,
                   group.policy.load_includes_battery_charging,
                   group.sources.battery_power_entity if group.policy.load_includes_battery_charging else None,
                   group.policy.battery_positive if group.policy.load_includes_battery_charging else None,
                   [(key, devices[key].settings.get("climate_entity"),
                     devices[key].settings.get("outdoor_temperature_entity"))
                    for key in members if key in devices]]
        # Do not invalidate history for temperature, fan, SOC or forecast changes.
        signature = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        model = self.groups.get(group.group_id)
        if model is None or model.context != signature:
            model = self.groups[group.group_id] = GroupAnalysis(context=signature)
        valid = bool(members) and group.policy.load_scope == "includes_all_members"
        readings: dict[str, Conditions | None] = {}
        for key in members:
            coordinator = devices.get(key)
            climate = self.hass.states.get(coordinator.settings["climate_entity"]) if coordinator else None
            if climate is None or climate.state not in ("off", "heat", "cool"):
                valid = False
                continue
            condition = self.conditions(coordinator) if climate.state != "off" else None
            if climate.state != "off" and condition is None:
                valid = False
            readings[key] = condition
        watts = snapshot.energy.load
        if group.policy.load_includes_battery_charging:
            battery = self.hass.states.get(group.sources.battery_power_entity)
            stamp = battery.last_reported.timestamp() if battery else None
            if (stamp is None or snapshot.load_reported_at is None
                    or not 0 <= snapshot.now - stamp <= 90
                    or abs(stamp - snapshot.load_reported_at) > 30
                    or snapshot.energy.battery is None):
                valid = False
            elif watts is not None:
                watts -= max(0, -snapshot.energy.battery)
        model.observe(now=snapshot.now, reported=snapshot.load_reported_at,
                      watts=watts, members=readings, valid=valid, adaptive=False)
        stamp = snapshot.load_reported_at
        if valid and stamp is not None and watts is not None and watts >= 0 and 0 <= snapshot.now-stamp <= 90:
            key = (signature, int(stamp//60))
            if self.queued_minutes.get(group.group_id) != key:
                payload = json.dumps({k: asdict(v) if v else None for k, v in readings.items()}, allow_nan=False)
                if len(payload.encode("utf-8")) <= MAX_PAYLOAD:
                    self.pending.append((group.group_id, signature, stamp, watts, payload))
                    self.queued_minutes[group.group_id] = key
        else:
            model.adaptive.status = "invalid_data"
        if group.policy.load_scope != "includes_all_members":
            model.status = "unsupported_load"
            model.adaptive.status = "unsupported_load"
        live_groups = {g.group_id for g in registry.groups}
        self.groups = {k: v for k, v in self.groups.items() if k in live_groups}
        self.queued_minutes = {k: v for k, v in self.queued_minutes.items() if k in live_groups}
        if self.timer_unsub is None:
            self.timer_unsub = async_track_time_interval(self.hass, self.async_process, timedelta(minutes=5))
        if snapshot.now-self.last_sql >= 300 and (self.sql_task is None or self.sql_task.done()):
            self.last_sql = snapshot.now
            self.sql_task = self.hass.async_create_task(self.async_process())
        if snapshot.now - self.last_save >= 60:
            self.last_save = snapshot.now
            self.store.async_delay_save(self.stored, 1)

    def view(self, group_id: str, coordinator: Any) -> dict[str, Any]:
        model = self.groups.get(group_id, GroupAnalysis())
        now = dt_util.utcnow().timestamp()
        phase = "startup" if model.started is None or now - model.started < 600 else "steady"
        result = model.estimate(coordinator.device_id, self.conditions(coordinator, phase=phase), now)
        result["adaptive"] = model.adaptive.view(coordinator.device_id, self.conditions(coordinator), now)
        result["adaptive"]["status"] = self.error or result["adaptive"]["status"]
        result["status"] = self.error or result["status"]
        return result

    def background_view(self, group_id: str) -> dict[str, Any]:
        model = self.groups.get(group_id, GroupAnalysis())
        now = dt_util.utcnow().timestamp()
        model.prune(now)
        recent = [v for t, v in model.background if now - t <= 86400]
        return {"watts": round(median(recent), 1) if recent else None,
                "samples": len(recent), "status": self.error or model.status,
                "updated_at": model.background[-1][0] if model.background else None}
