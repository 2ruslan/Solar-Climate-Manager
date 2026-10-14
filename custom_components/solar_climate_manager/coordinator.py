"""Event-driven observation and real climate control."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .climate_control import (
    ACKNOWLEDGEMENT_SECONDS,
    COMMAND_TIMEOUT_SECONDS,
    TARGET_UPDATE_SECONDS,
    acknowledgement_changes,
    compensated_target,
    matches_acknowledgement,
    normalized_target,
    temperature_matches,
)
from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, POWER_SOURCES, REMOVED_SETTINGS
from .manual import control_fingerprint, pause_active
from .model import evaluate, is_fresh, temperature_celsius
from .power import power_watts, read_power, signed_power_watts, soc_percent
from .settings import configuration_values
from .strategy import (
    ControlState,
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
        self.settings = configuration_values(entry.data, entry.options, DEFAULTS, REMOVED_SETTINGS)
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.demand = False
        self.signature = None
        self.control = ControlState()
        self.command_task = None
        self.command_contexts = {}
        self.expected_updates = []
        self.unconfirmed_start = False
        self.command_error = "none"
        self.closed = False
        self.last_command = None
        self.last_target_update = None
        self.manual_date = None
        self.policy_signature = dict(self.settings)

    async def async_initialize(self):
        saved = await self.store.async_load() or {}
        self.signature = self._signature()
        if saved.get("signature") == self.signature:
            self.demand = saved.get("demand") is True
        self.manual_date = saved.get("manual_date")
        if saved.get("policy_signature") == self.policy_signature:
            self.control.restore(saved.get("control"), dt_util.utcnow().timestamp())
        elif isinstance(saved.get("control"), dict):
            previous = saved.get("control")
            now = dt_util.utcnow().timestamp()
            self.control.last_stop = (
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
                "operation_mode",
            )
        ]

    async def async_shutdown(self):
        """Complete persistence before a replacement coordinator loads the store."""
        self.closed = True
        await self._cancel_command()
        await self.store.async_save(self._stored_state())

    def _stored_state(self):
        return {
            "demand": self.demand,
            "signature": self.signature,
            "manual_date": self.manual_date,
            "control": serialize(self.control),
            "policy_signature": self.policy_signature,
        }

    @callback
    def _state_changed(self, event):
        if event.data.get("entity_id") == self.settings["climate_entity"]:
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            before = control_fingerprint(old.state, old.attributes) if old else None
            after = control_fingerprint(new.state, new.attributes) if new else None
            context = getattr(new, "context", None)
            self._prune_acknowledgements()
            own = (
                context is not None
                and not getattr(context, "user_id", None)
                and (
                    context.id in self.command_contexts
                    or context.parent_id in self.command_contexts
                )
            )
            if before is not None and after is not None and before != after:
                own = own or self._matches_expected_update(old, new, context)
            if before is not None and after is not None and before != after and not own:
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
        climate_valid = (
            climate is not None
            and climate.state not in ("unknown", "unavailable")
            and settings["hvac_mode"] in climate.attributes.get("hvac_modes", [])
        )
        ac_temperature = (
            temperature_celsius(
                climate.attributes.get("current_temperature"),
                climate.attributes.get("temperature_unit", self.hass.config.units.temperature_unit),
            )
            if climate_valid
            else None
        )
        raw_target = compensated_target(settings["target_temperature"], temperature, ac_temperature)
        ac_target = None
        if raw_target is not None:
            try:
                command_target = normalized_target(
                    raw_target,
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                    clamp=True,
                )
                ac_target = temperature_celsius(
                    command_target, self.hass.config.units.temperature_unit
                )
            except ValueError:
                pass
        decision = evaluate(
            temperature,
            target=settings["target_temperature"],
            hysteresis=settings["hysteresis"],
            mode=settings["hvac_mode"],
            previous_demand=self.demand,
            enabled=settings["operation_mode"] != "disabled",
            climate_valid=climate_valid and ac_temperature is not None,
        )
        if self.demand != decision.demand:
            self.demand = decision.demand
        data = {
            "temperature": temperature,
            "ac_temperature": ac_temperature,
            "ac_set_temperature": temperature_celsius(
                climate.attributes.get("temperature"),
                climate.attributes.get("temperature_unit", self.hass.config.units.temperature_unit),
            )
            if climate_valid
            else None,
            "temperature_offset": (ac_temperature - temperature)
            if ac_temperature is not None and temperature is not None
            else None,
            "ac_target_temperature": ac_target,
            "demand": decision.demand,
            "invalid_data": not decision.data_valid,
            "reason": decision.reason,
            "automation_mode": settings["operation_mode"],
            "control_allowed": False,
            "command_error": self.command_error,
            "command_failed": self.command_error != "none",
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
            max(0, -data["battery_power"]) if data["battery_power"] is not None else None
        )
        data["battery_charge_power"] = measured_charge
        data["house_load_power"] = house_load_power(
            data["load_power"], measured_charge, settings["load_includes_battery_charging"]
        )
        limit_id = settings.get("grid_import_limit_entity")
        limit_state = self.hass.states.get(limit_id) if limit_id else None
        # This is a setting, not a periodically reported measurement.
        data["grid_import_limit"] = (
            power_watts(limit_state.state, limit_state.attributes.get("unit_of_measurement"))
            if limit_state
            else None
        )
        limit_active = bool(limit_id) and data["grid_import_limit"] != 0
        data["grid_import_limit_active"] = limit_active
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
        ac_valid = (not settings.get("ac_power_entity") or data["ac_power"] is not None) and data[
            "house_load_power"
        ] is not None
        forecast_keys = ("forecast_power_now", "forecast_power_30m", "forecast_power_60m")
        forecasts = tuple(data[key] for key in forecast_keys)
        snapshot = EnergySnapshot(
            pv=data["pv_power"],
            load=data["load_power"],
            soc=data["soc"],
            battery=data["battery_power"],
            grid_power=data["grid_power"],
            grid_import_limit=data["grid_import_limit"],
            grid_limit_configured=limit_active,
            grid=grid,
            forecasts=forecasts,
            actual_ac_power=actual_ac,
            ac_power_valid=ac_valid,
            temperature_valid=decision.data_valid,
            schedule_allowed=schedule is True,
        )
        climate_available = climate is not None and climate.state not in ("unknown", "unavailable")
        actual_running = climate.state != "off" if climate_available else self.control.running
        if actual_running != self.control.running:
            if actual_running:
                self.control.last_start = now.timestamp()
            else:
                self.control.last_stop = now.timestamp()
        self.control.running = actual_running
        cycle_times = self.control.last_start, self.control.last_stop
        strategy = decide(
            snapshot,
            self.control,
            settings,
            now=now.timestamp(),
            demand=decision.demand,
            enabled=settings["operation_mode"] != "disabled",
            manual=manual,
        )
        data.update(
            {
                "grid_available": grid,
                "energy_allowed": strategy.energy_allowed,
                "energy_reason": strategy.energy_reason,
                "grid_import_margin": strategy.grid_import_margin,
                "running": actual_running if climate_available else None,
                "strategy_action": strategy.action,
                "strategy_reason": strategy.reason,
                "solar_margin": strategy.solar_margin,
                "average_solar_margin": strategy.average_solar_margin,
                "forecast_margin": strategy.forecast_margin,
                "seconds_to_start": round(strategy.seconds_to_start)
                if strategy.seconds_to_start is not None
                else None,
                "seconds_to_stop": round(strategy.seconds_to_stop)
                if strategy.seconds_to_stop is not None
                else None,
                "manual_pause": manual,
                "manual_status": "disabled"
                if settings["operation_mode"] == "disabled"
                else "manual_today"
                if manual
                else "automatic",
                "energy_data_invalid": (
                    grid is True
                    and limit_active
                    and (data["grid_import_limit"] is None or data["grid_power"] is None)
                )
                or any(
                    value is None
                    for value in (
                        data["soc"],
                        data["battery_power"],
                        grid,
                    )
                )
                or (
                    grid is False
                    and (data["pv_power"] is None or data["load_power"] is None or not ac_valid)
                ),
            }
        )
        data["control_allowed"] = (
            settings["operation_mode"] == "control" and climate_valid and not manual
        )
        self.desired_running = strategy.running
        # Persist actual cycle state, not the decision awaiting a device update.
        self.control.running = actual_running
        self.control.last_start, self.control.last_stop = cycle_times
        if stored_before != self._stored_state():
            self.store.async_delay_save(self._stored_state, 1)
        if self.data != data:
            if self.data is None or self.data.get("strategy_reason") != strategy.reason:
                LOGGER.debug(
                    "Entry %s: %s (%s)", self.entry.entry_id, strategy.action, strategy.reason
                )
            if self.data is None or self.data.get("reason") != decision.reason:
                LOGGER.debug("Entry %s: %s", self.entry.entry_id, decision.reason)
            self.async_set_updated_data(data)
        if data["control_allowed"] and not self.closed and self.command_task is None:
            self.command_task = self.entry.async_create_task(
                self.hass, self._async_control(), "climate control", eager_start=False
            )

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

    async def _cancel_command(self):
        if self.command_task is not None:
            self.command_task.cancel()
            try:
                await self.command_task
            except asyncio.CancelledError:
                pass
            self.command_task = None

    async def async_set_mode(self, mode):
        self.settings["operation_mode"] = mode
        await self._cancel_command()
        self.last_command = None
        self.control.window.clear()
        self.signature = self._signature()
        self.policy_signature = dict(self.settings)
        options = {**self.entry.options, "operation_mode": mode}
        options.pop("enabled", None)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self._evaluate()

    def _prune_acknowledgements(self):
        now = dt_util.utcnow().timestamp()
        self.command_contexts = {
            key: expires for key, expires in self.command_contexts.items() if expires >= now
        }
        self.expected_updates = [
            item for item in self.expected_updates if item["expires"] >= now and item["remaining"]
        ]

    def _matches_expected_update(self, old, new, context):
        # Explicit user commands and unrelated automation contexts remain manual.
        if context and (getattr(context, "user_id", None) or getattr(context, "parent_id", None)):
            return False
        changes = acknowledgement_changes(old, new)
        for item in self.expected_updates:
            if matches_acknowledgement(changes, item["remaining"]):
                for key in changes:
                    item["remaining"].pop(key)
                return True
        return False

    def _set_command_error(self, error):
        self.command_error = error
        if self.data and self.data.get("command_error") != error:
            self.async_set_updated_data(
                {**self.data, "command_error": error, "command_failed": error != "none"}
            )

    def _control_command(self, climate):
        if self.desired_running:
            try:
                normalized_target(
                    self.settings["target_temperature"],
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                )
                target = normalized_target(
                    compensated_target(
                        self.settings["target_temperature"],
                        self.data["temperature"],
                        self.data["ac_temperature"],
                    ),
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                    clamp=True,
                )
            except ValueError as error:
                self._set_command_error(str(error))
                return None
            mode = self.settings["hvac_mode"]
            if climate.state == mode and temperature_matches(
                climate.attributes.get("temperature"), target
            ):
                self.last_command = None
                self.unconfirmed_start = False
                self._set_command_error("none")
                return None
            return "set_temperature", {"hvac_mode": mode, "temperature": target}
        if climate.state == "off" and not self.unconfirmed_start:
            self.last_command = None
            self._set_command_error("none")
            return None
        return "set_hvac_mode", {"hvac_mode": "off"}

    async def _async_control(self):
        try:
            while (
                not self.closed
                and self.settings["operation_mode"] == "control"
                and self.data["control_allowed"]
            ):
                climate = self.hass.states.get(self.settings["climate_entity"])
                if climate is None or climate.state in ("unknown", "unavailable"):
                    return
                if pause_active(self.manual_date, dt_util.now().date()):
                    return
                command = self._control_command(climate)
                if command is None:
                    return
                service, payload = command
                key = (service, tuple(payload.items()))
                now = dt_util.utcnow().timestamp()
                if (
                    self.last_command
                    and self.last_command[0] == key
                    and now - self.last_command[1] < 30
                ):
                    return
                if (
                    service == "set_temperature"
                    and self.command_error == "none"
                    and self.last_target_update is not None
                    and now - self.last_target_update < TARGET_UPDATE_SECONDS
                ):
                    return
                self._prune_acknowledgements()
                context = Context()
                expires = now + ACKNOWLEDGEMENT_SECONDS
                self.command_contexts[context.id] = expires
                remaining = {
                    name: value
                    for name, value in payload.items()
                    if (climate.state if name == "hvac_mode" else climate.attributes.get(name))
                    != value
                }
                self.expected_updates.append({"expires": expires, "remaining": remaining})
                self.last_command = (key, now)
                if service == "set_temperature":
                    self.last_target_update = now
                    self.unconfirmed_start = True
                try:
                    async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
                        await self.hass.services.async_call(
                            "climate",
                            service,
                            {"entity_id": self.settings["climate_entity"], **payload},
                            blocking=True,
                            context=context,
                        )
                except (HomeAssistantError, TimeoutError):
                    self._set_command_error("service_error")
                    LOGGER.exception("Climate command failed for entry %s", self.entry.entry_id)
                else:
                    self._set_command_error("none")
                    if service == "set_hvac_mode":
                        self.unconfirmed_start = False
                # Recompute after every service call: both state and timer deadlines
                # may have changed. A stop overrides an unconfirmed physical start.
                self._evaluate()
        finally:
            self.command_task = None
