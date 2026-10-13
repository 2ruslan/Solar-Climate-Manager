"""Event-driven diagnostics and asynchronous persistence, without climate commands."""

import logging
from datetime import timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, POWER_SOURCES, REMOVED_FORECAST_SETTINGS
from .manual import control_fingerprint, pause_active
from .model import evaluate, is_fresh, temperature_celsius
from .power import power_watts, read_power, signed_power_watts, soc_percent
from .strategy import (
    DemoState,
    EnergySnapshot,
    decide,
    house_load_power,
    serialize,
    valid_timestamp,
)

LOGGER = logging.getLogger(__name__)


class SolarClimateCoordinator(DataUpdateCoordinator):
    """Separate runtime state for each selected climate entity."""

    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry, always_update=False)
        self.entry = entry
        self.settings = {**DEFAULTS, **entry.data, **entry.options}
        self.settings = {
            key: value
            for key, value in self.settings.items()
            if key not in REMOVED_FORECAST_SETTINGS
        }
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.demand = False
        self.signature = None
        self.demo = DemoState()
        self.manual_date = None
        self.policy_signature = dict(self.settings)

    async def async_initialize(self):
        saved = await self.store.async_load() or {}
        self.signature = self._signature()
        if saved.get("signature") == self.signature:
            self.demand = saved.get("demand") is True
        self.manual_date = saved.get("manual_date")
        if saved.get("policy_signature") == self.policy_signature:
            self.demo.restore(saved.get("demo"), dt_util.utcnow().timestamp())
        elif isinstance(saved.get("demo"), dict):
            previous = saved["demo"]
            now = dt_util.utcnow().timestamp()
            self.demo.last_stop = (
                now
                if previous.get("running") is True
                else valid_timestamp(previous.get("last_stop"), now)
            )
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass,
                [self.settings["temperature_entity"], self.settings["climate_entity"]]
                + [self.settings[key] for key in OPTIONAL_SOURCES if self.settings.get(key)],
                self._state_changed,
            )
        )
        self.entry.async_on_unload(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=30))
        )
        self._evaluate()

    def _signature(self):
        return [
            self.settings[key]
            for key in (
                "temperature_entity",
                "hvac_mode",
                "target_temperature",
                "hysteresis",
                "enabled",
            )
        ]

    async def async_shutdown(self):
        """Complete persistence before a replacement coordinator loads the store."""
        await self.store.async_save(self._stored_state())

    def _stored_state(self):
        return {
            "demand": self.demand,
            "signature": self.signature,
            "manual_date": self.manual_date,
            "demo": serialize(self.demo),
            "policy_signature": self.policy_signature,
        }

    @callback
    def _state_changed(self, event):
        if (
            event.data.get("entity_id") == self.settings["climate_entity"]
            and self.settings["pause_on_external_change"]
        ):
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            before = control_fingerprint(old.state, old.attributes) if old else None
            after = control_fingerprint(new.state, new.attributes) if new else None
            if before is not None and after is not None and before != after:
                self.manual_date = dt_util.now().date().isoformat()
                self.store.async_delay_save(self._stored_state, 1)
        self._evaluate()

    @callback
    def _tick(self, now):
        self._evaluate()

    @callback
    def _evaluate(self):
        settings = self.settings
        stored_before = self._stored_state()
        today = dt_util.now().date()
        manual = pause_active(self.manual_date, today)
        if self.manual_date and not manual:
            self.manual_date = None
        state = self.hass.states.get(settings["temperature_entity"])
        climate = self.hass.states.get(settings["climate_entity"])
        temperature = (
            temperature_celsius(state.state, state.attributes.get("unit_of_measurement"))
            if state
            else None
        )
        fresh = state is not None and is_fresh(
            dt_util.utcnow(), state.last_reported, settings["max_data_age"]
        )
        climate_valid = (
            climate is not None
            and climate.state not in ("unknown", "unavailable")
            and settings["hvac_mode"] in climate.attributes.get("hvac_modes", [])
        )
        decision = evaluate(
            temperature,
            target=settings["target_temperature"],
            hysteresis=settings["hysteresis"],
            mode=settings["hvac_mode"],
            previous_demand=self.demand,
            fresh=fresh,
            enabled=settings["enabled"],
            climate_valid=climate_valid,
        )
        if self.demand != decision.demand:
            self.demand = decision.demand
        data = {
            "temperature": temperature if fresh else None,
            "demand": decision.demand,
            "invalid_data": not decision.data_valid,
            "reason": decision.reason,
            "automation_mode": "observation" if settings["enabled"] else "disabled",
            "control_allowed": False,
        }
        now = dt_util.utcnow()
        for key, source_key in POWER_SOURCES.items():
            source_id = settings.get(source_key)
            source = self.hass.states.get(source_id) if source_id else None
            data[key] = (
                (
                    read_power(
                        source.state,
                        source.attributes.get("unit_of_measurement"),
                        now=now,
                        reported=source.last_reported,
                        max_age=settings["power_max_data_age"],
                    )
                    if key == "pv_power"
                    else power_watts(source.state, source.attributes.get("unit_of_measurement"))
                )
                if source
                else None
            )
        for key in (
            "load_power",
            "battery_power",
            "battery_charge_power",
            "grid_power",
            "soc",
            "ac_power",
        ):
            data[key] = self._energy_value(f"{key}_entity", now, key)
        if data["battery_power"] is not None and settings["battery_positive"] == "charge":
            data["battery_power"] *= -1
        if data["grid_power"] is not None and settings["grid_positive"] == "export":
            data["grid_power"] *= -1
        measured_charge = (
            data["battery_charge_power"]
            if settings.get("battery_charge_power_entity")
            else max(0, -data["battery_power"])
            if data["battery_power"] is not None
            else None
        )
        data["house_load_power"] = house_load_power(
            data["load_power"], measured_charge, settings["load_includes_battery_charging"]
        )
        grid = self._binary_value("grid_available_entity", now, settings["grid_max_data_age"])
        if grid is not None and not settings["grid_on_means_available"]:
            grid = not grid
        schedule = (
            self._binary_value("schedule_entity", now, None)
            if settings.get("schedule_entity")
            else True
        )
        actual_ac = data["ac_power"]
        if actual_ac is None:
            actual_ac = (
                settings["estimated_ac_power"]
                if climate and climate.attributes.get("hvac_action") in ("heating", "cooling")
                else 0
            )
        ac_valid = (
            (not settings.get("ac_power_entity") or data["ac_power"] is not None)
            and (not settings.get("battery_charge_power_entity") or measured_charge is not None)
            and data["house_load_power"] is not None
        )
        forecast_keys = ("forecast_power_now", "forecast_power_30m", "forecast_power_60m")
        forecasts = tuple(data[key] for key in forecast_keys)
        # Multiple demo entries share their virtual power reservation if sources match.
        reserved = sum(
            other.runtime_data.settings["estimated_ac_power"]
            for other in self.hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != self.entry.entry_id
            and getattr(other, "runtime_data", None)
            and getattr(other.runtime_data, "demo", None)
            and other.runtime_data.demo.running
            and settings.get("pv_power_entity")
            and other.runtime_data.settings.get("pv_power_entity")
            == settings.get("pv_power_entity")
            and other.runtime_data.settings.get("load_power_entity")
            == settings.get("load_power_entity")
        )
        snapshot = EnergySnapshot(
            pv=data["pv_power"],
            load=data["load_power"],
            soc=data["soc"],
            battery=data["battery_power"],
            battery_charge=measured_charge,
            grid_power=data["grid_power"],
            grid=grid,
            forecasts=forecasts,
            actual_ac_power=actual_ac,
            other_virtual_power=reserved,
            temperature_valid=decision.data_valid and ac_valid,
            schedule_allowed=schedule is True,
        )
        strategy = decide(
            snapshot,
            self.demo,
            settings,
            now=now.timestamp(),
            demand=decision.demand,
            enabled=settings["enabled"],
            manual=manual,
        )
        data.update(
            {
                "grid_available": grid,
                "energy_allowed": strategy.energy_allowed,
                "virtual_running": strategy.virtual_running,
                "demo_action": strategy.action,
                "strategy_reason": strategy.reason,
                "solar_margin": strategy.solar_margin,
                "forecast_margin": strategy.forecast_margin,
                "seconds_to_start": round(strategy.seconds_to_start)
                if strategy.seconds_to_start is not None
                else None,
                "seconds_to_stop": round(strategy.seconds_to_stop)
                if strategy.seconds_to_stop is not None
                else None,
                "manual_pause": manual,
                "manual_status": "disabled"
                if not settings["enabled"]
                else "manual_today"
                if manual
                else "automatic",
                "energy_data_invalid": any(
                    value is None
                    for value in (
                        data["pv_power"],
                        data["load_power"],
                        data["soc"],
                        data["battery_power"],
                        data["grid_power"],
                        grid,
                    )
                )
                or not ac_valid
                or settings["require_forecast"]
                and any(value is None for value in snapshot.forecasts),
            }
        )
        if stored_before != self._stored_state():
            self.store.async_delay_save(self._stored_state, 1)
        if self.data != data:
            if self.data is None or self.data.get("strategy_reason") != strategy.reason:
                LOGGER.debug(
                    "Demo entry %s: %s (%s)", self.entry.entry_id, strategy.action, strategy.reason
                )
            if self.data is None or self.data.get("reason") != decision.reason:
                LOGGER.debug("Entry %s: %s", self.entry.entry_id, decision.reason)
            self.async_set_updated_data(data)

    def _energy_value(self, source_key, now, kind):
        entity_id = self.settings.get(source_key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or not is_fresh(
            now, state.last_reported, self.settings["power_max_data_age"]
        ):
            return None
        unit = state.attributes.get("unit_of_measurement")
        value = (
            soc_percent(state.state, unit)
            if kind == "soc"
            else signed_power_watts(state.state, unit)
        )
        return (
            value
            if kind in ("battery_power", "grid_power", "soc") or value is not None and value >= 0
            else None
        )

    def _binary_value(self, source_key, now, max_age):
        entity_id = self.settings.get(source_key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state not in ("on", "off"):
            return None
        if max_age is not None and not is_fresh(now, state.last_reported, max_age):
            return None
        return state.state == "on"
