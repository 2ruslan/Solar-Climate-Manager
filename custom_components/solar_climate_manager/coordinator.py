"""Event-driven observation and real climate control."""

import asyncio
import logging
from dataclasses import replace
from datetime import timedelta

from homeassistant.core import Context, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters.sources import climate_temperature, read_sources
from .adapters.storage import create_store, demand_signature, restore_runtime, stored_state
from .climate_control import (
    ACKNOWLEDGEMENT_SECONDS,
    COMMAND_TIMEOUT_SECONDS,
    TARGET_UPDATE_SECONDS,
    acknowledgement_changes,
    compensated_target,
    compensation_needed,
    matches_acknowledgement,
    normalized_target,
    temperature_matches,
)
from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, REMOVED_SETTINGS
from .domain.types import (
    CommandState,
    ControlIntent,
    DeviceConfig,
    EnergyPolicyConfig,
    ExpectedUpdate,
    ObservedDeviceState,
    PolicyState,
)
from .manual import control_fingerprint, pause_active
from .model import evaluate
from .presentation import build_state
from .settings import OPERATION_MODES, configuration_values
from .strategy import decide

LOGGER = logging.getLogger(__name__)


class SolarClimateCoordinator(DataUpdateCoordinator):
    """Separate runtime state for each selected climate entity."""

    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry, always_update=False)
        self.entry = entry
        self.settings = configuration_values(entry.data, entry.options, DEFAULTS, REMOVED_SETTINGS)
        self.settings.pop("temporary_previous_mode", None)
        self.settings.pop("temporary_block_date", None)
        self.store = create_store(hass, entry.entry_id)
        self.demand = False
        self.signature = None
        self.observed = ObservedDeviceState()
        self.policy = PolicyState()
        self.intent = ControlIntent()
        self.device = DeviceConfig.from_settings(self.settings)
        self.command = CommandState()
        self.command_task = None
        self.closed = False
        self.manual_date = None
        self.previous_mode = None
        self.policy_signature = dict(self.settings)

    async def async_initialize(self):
        self.signature = demand_signature(self.settings)
        restored = restore_runtime(
            await self.store.async_load(), settings=self.settings,
            options=self.entry.options, now=dt_util.utcnow().timestamp(),
        )
        self.demand = restored.demand
        self.manual_date = restored.manual_date
        self.previous_mode = restored.previous_mode
        self.observed = restored.observed
        self.policy = restored.policy
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

    async def async_shutdown(self):
        """Complete persistence before a replacement coordinator loads the store."""
        self.closed = True
        await self._cancel_command()
        await self.store.async_save(self._stored_state())

    def _stored_state(self):
        return stored_state(
            demand=self.demand, signature=self.signature, manual_date=self.manual_date,
            observed=self.observed, policy=self.policy, policy_signature=self.policy_signature,
        )

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
                    context.id in self.command.contexts
                    or context.parent_id in self.command.contexts
                )
            )
            if before is not None and after is not None and before != after:
                own = own or self._matches_expected_update(old, new, context)
            if before is not None and after is not None and before != after and not own:
                self._set_operation_mode("temporary_block")
                self.store.async_delay_save(self._stored_state, 1)
        self._evaluate()

    @callback
    def _tick(self, now):
        self._evaluate()

    @callback
    def _evaluate(self):
        settings = self.settings
        self.device = DeviceConfig.from_settings(settings)
        energy_config = EnergyPolicyConfig.from_settings(settings)
        stored_before = self._stored_state()
        today = dt_util.now().date()
        manual = pause_active(self.manual_date, today)
        if settings["operation_mode"] == "temporary_block" and not manual:
            self._set_operation_mode(self.previous_mode or "observation")
        elif manual and settings["operation_mode"] != "temporary_block":
            # Migrate the separate manual pause used by older versions.
            self._set_operation_mode("temporary_block")
        elif self.manual_date and not manual:
            self.manual_date = None
        now = dt_util.utcnow()
        sources = read_sources(
            self.hass.states.get, settings, self.device,
            self.hass.config.units.temperature_unit, now,
        )
        decision = evaluate(
            sources.temperature,
            target=self.device.target_temperature,
            hysteresis=self.device.hysteresis,
            mode=self.device.hvac_mode,
            previous_demand=self.demand,
            enabled=settings["operation_mode"] != "disabled",
            climate_valid=sources.climate_valid and sources.ac_target_temperature is not None,
        )
        self.demand = decision.demand
        if sources.running is not None:
            self.observed = self.observed.observe(sources.running, now.timestamp())
        evaluation = decide(
            sources.energy, self.observed, self.policy, energy_config,
            now=now.timestamp(), demand=decision.demand,
            enabled=settings["operation_mode"] != "disabled", manual=manual,
        )
        self.policy = evaluation.policy
        strategy = evaluation.decision
        self.intent = strategy.intent
        data = build_state(
            sources, decision, strategy, self.policy,
            operation_mode=settings["operation_mode"], manual=manual,
            command_error=self.command.error,
            control_allowed=(
                settings["operation_mode"] == "control" and sources.climate_valid and not manual
            ),
        )
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

    async def _cancel_command(self):
        if self.command_task is not None:
            self.command_task.cancel()
            try:
                await self.command_task
            except asyncio.CancelledError:
                pass
            self.command_task = None

    @callback
    def _set_operation_mode(self, mode):
        """Persist the visible mode and its midnight return state together."""
        if mode not in OPERATION_MODES:
            raise ValueError(mode)
        options = dict(self.entry.options)
        if mode == "temporary_block":
            if self.settings["operation_mode"] != "temporary_block":
                self.previous_mode = self.settings["operation_mode"]
            self.manual_date = dt_util.now().date().isoformat()
            options["temporary_previous_mode"] = self.previous_mode or "observation"
            options["temporary_block_date"] = self.manual_date
        else:
            self.manual_date = None
            self.previous_mode = None
            options.pop("temporary_previous_mode", None)
            options.pop("temporary_block_date", None)
        self.settings["operation_mode"] = mode
        self.device = replace(self.device, operation_mode=mode)
        self.command.last_command = None
        self.policy.window.clear()
        self.signature = demand_signature(self.settings)
        self.policy_signature = dict(self.settings)
        options["operation_mode"] = mode
        options.pop("enabled", None)
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def async_set_mode(self, mode):
        self._set_operation_mode(mode)
        await self._cancel_command()
        self._evaluate()
        await self.store.async_save(self._stored_state())

    def _prune_acknowledgements(self):
        now = dt_util.utcnow().timestamp()
        self.command.contexts = {
            key: expires for key, expires in self.command.contexts.items() if expires >= now
        }
        self.command.expected_updates = [
            item for item in self.command.expected_updates if item.expires >= now and item.remaining
        ]

    def _matches_expected_update(self, old, new, context):
        # Explicit user commands and unrelated automation contexts remain manual.
        if context and (getattr(context, "user_id", None) or getattr(context, "parent_id", None)):
            return False
        changes = acknowledgement_changes(old, new)
        for item in self.command.expected_updates:
            if matches_acknowledgement(changes, item.remaining):
                for key in changes:
                    item.remaining.pop(key)
                return True
        return False

    def _set_command_error(self, error):
        self.command.error = error
        if self.data and self.data.get("command_error") != error:
            self.async_set_updated_data(
                {**self.data, "command_error": error, "command_failed": error != "none"}
            )

    def _control_command(self, climate):
        if self.intent.running:
            try:
                normalized_target(
                    self.device.target_temperature,
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                )
                target = normalized_target(
                    compensated_target(
                        self.device.target_temperature,
                        self.data["temperature"],
                        self.data["ac_temperature"],
                    ),
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                    clamp=True,
                    bounds_c=(
                        self.device.ac_min_temperature, self.device.ac_max_temperature,
                    ),
                )
            except ValueError as error:
                self._set_command_error(str(error))
                return None
            mode = self.device.hvac_mode
            current_target = climate_temperature(
                climate, "temperature", self.hass.config.units.temperature_unit
            )
            current_valid = False
            if current_target is not None:
                try:
                    bounded_current = normalized_target(
                        current_target, climate.attributes,
                        self.hass.config.units.temperature_unit, clamp=True,
                        bounds_c=(
                            self.device.ac_min_temperature,
                            self.device.ac_max_temperature,
                        ),
                    )
                    current_valid = temperature_matches(
                        climate.attributes.get("temperature"), bounded_current
                    )
                except ValueError:
                    pass
            if climate.state == mode and (
                temperature_matches(climate.attributes.get("temperature"), target)
                or current_valid and self.command.error == "none" and not compensation_needed(
                    current_target, self.data["ac_temperature"], mode
                )
            ):
                self.command.last_command = None
                self.command.unconfirmed_start = False
                self._set_command_error("none")
                return None
            return "set_temperature", {"hvac_mode": mode, "temperature": target}
        if climate.state == "off" and not self.command.unconfirmed_start:
            self.command.last_command = None
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
                    self.command.last_command
                    and self.command.last_command[0] == key
                    and now - self.command.last_command[1] < 30
                ):
                    return
                if (
                    service == "set_temperature"
                    and self.command.error == "none"
                    and self.command.last_target_update is not None
                    and now - self.command.last_target_update < TARGET_UPDATE_SECONDS
                ):
                    return
                self._prune_acknowledgements()
                context = Context()
                expires = now + ACKNOWLEDGEMENT_SECONDS
                self.command.contexts[context.id] = expires
                remaining = {
                    name: value
                    for name, value in payload.items()
                    if (climate.state if name == "hvac_mode" else climate.attributes.get(name))
                    != value
                }
                self.command.expected_updates.append(ExpectedUpdate(expires, remaining))
                self.command.last_command = (key, now)
                if service == "set_temperature":
                    self.command.last_target_update = now
                    self.command.unconfirmed_start = True
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
                        self.command.unconfirmed_start = False
                # Recompute after every service call: both state and timer deadlines
                # may have changed. A stop overrides an unconfirmed physical start.
                self._evaluate()
        finally:
            self.command_task = None
