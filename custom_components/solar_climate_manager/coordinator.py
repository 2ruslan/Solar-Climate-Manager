"""Event-driven observation and real climate control."""

import logging
from dataclasses import replace
from datetime import timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters.sources import read_sources
from .adapters.storage import create_store
from .climate_control import normalized_target
from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, REMOVED_SETTINGS
from .domain.learning import PowerLearning
from .domain.types import DeviceConfig
from .history import DiagnosticHistory
from .manual import control_fingerprint
from .model import temperature_celsius
from .presentation import build_state
from .runtime.commands import CommandExecutor
from .runtime.device import DeviceRuntime
from .settings import configuration_values

LOGGER = logging.getLogger(__name__)


class SolarClimateCoordinator(DataUpdateCoordinator):
    """Separate runtime state for each selected climate entity."""

    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry, always_update=False)
        self.history = DiagnosticHistory()
        self.group_observer = None
        self.group_manager = None
        self.entry = entry
        self.device_id = entry.data.get("device_id", entry.entry_id)
        self.settings = configuration_values(entry.data, entry.options, DEFAULTS, REMOVED_SETTINGS)
        self.settings.pop("temporary_previous_mode", None)
        self.settings.pop("temporary_block_date", None)
        self.store = create_store(hass, entry.entry_id)
        self.runtime = DeviceRuntime(self.settings)
        self.last_temperature = None
        self.power_learning = PowerLearning()
        self.commands = CommandExecutor(
            hass, entry, self.runtime, lambda: self.data, self._evaluate, self._publish_command_error
        )

    @callback
    def async_set_updated_data(self, data):
        self.history.record(dt_util.utcnow().timestamp(), data, self.settings)
        super().async_set_updated_data(data)

    async def async_initialize(self):
        saved = await self.store.async_load()
        if isinstance(saved, dict) and saved.get("temperature_entity") == self.settings["temperature_entity"]:
            value = saved.get("last_temperature")
            if not isinstance(value, bool):
                self.last_temperature = temperature_celsius(value, "°C")
        now = dt_util.utcnow().timestamp()
        self.runtime.restore(saved, self.entry.options, now)
        self.power_learning.restore(saved.get("power_learning") if isinstance(saved, dict) else None, now)
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
        if self.group_observer is not None:
            self.group_observer.unregister(self)
        await self.commands.shutdown()
        if self.group_manager is not None:
            await self.group_manager.async_unregister(self)
        await self.store.async_save(self._stored_state())

    def _stored_state(self):
        return {
            **self.runtime.stored_state(), "power_learning": self.power_learning.stored(),
            "temperature_entity": self.settings["temperature_entity"],
            "last_temperature": self.last_temperature,
        }

    @callback
    def _state_changed(self, event):
        if self.commands.closed:
            return
        if event.data.get("entity_id") == self.settings["climate_entity"]:
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            self.commands.observe(new)
            before = control_fingerprint(old.state, old.attributes) if old else None
            after = control_fingerprint(new.state, new.attributes) if new else None
            own = (
                before is not None and after is not None and before != after
                and self.commands.is_own_update(old, new)
            )
            if before is not None and after is not None and before != after and not own:
                self._set_operation_mode("temporary_block")
                self.store.async_delay_save(self._stored_state, 1)
        self._evaluate()

    @callback
    def _tick(self, now):
        self._evaluate()

    @callback
    def _evaluate(self):
        if self.commands.closed:
            return
        settings = self.settings
        self.runtime.device = DeviceConfig.from_settings(settings)
        stored_before = self._stored_state()
        today = dt_util.now().date()
        mode = self.runtime.mode_for_date(today)
        if mode is not None:
            self._set_operation_mode(mode)
        now = dt_util.utcnow()
        sources = read_sources(
            self.hass.states.get, settings, self.runtime.device,
            self.hass.config.units.temperature_unit, now,
            last_temperature=self.last_temperature,
        )
        self.last_temperature = sources.temperature
        decision, strategy, manual = self.runtime.evaluate(sources, now, today)
        if decision.data_valid and not decision.demand:
            climate = self.hass.states.get(settings["climate_entity"])
            unit = self.hass.config.units.temperature_unit
            target = normalized_target(
                self.runtime.device.target_temperature, climate.attributes, unit, clamp=True,
                bounds_c=(self.runtime.device.ac_min_temperature, self.runtime.device.ac_max_temperature),
            )
            sources = replace(sources, ac_target_temperature=temperature_celsius(target, unit))
        data = build_state(
            sources, decision, strategy, self.runtime.policy,
            operation_mode=settings["operation_mode"], manual=manual,
            command_error=self.commands.state.error,
            control_allowed=(
                settings["operation_mode"] == "control" and sources.climate_valid and not manual
            ),
        )
        if self.group_manager is not None:
            data.update(self.group_manager.public_state(self))
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
        self.history.record(now.timestamp(), data, settings)
        self.commands.schedule()
        if self.group_manager is not None:
            self.group_manager.request_evaluation()
        if self.group_observer is not None:
            self.group_observer.evaluate()

    @callback
    def _set_operation_mode(self, mode):
        options = self.runtime.set_mode(mode, self.entry.options, dt_util.now().date())
        self.commands.state.last_command = None
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    async def async_set_mode(self, mode):
        self._set_operation_mode(mode)
        await self.commands.cancel()
        self._evaluate()
        await self.store.async_save(self._stored_state())

    def _publish_command_error(self, error):
        if self.data and self.data.get("command_error") != error:
            self.async_set_updated_data(
                {**self.data, "command_error": error, "command_failed": error != "none"}
            )
