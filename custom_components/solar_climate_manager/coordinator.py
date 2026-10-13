"""Event-driven diagnostics and asynchronous persistence, without climate commands."""

import logging
from datetime import timedelta

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN, POWER_SOURCES
from .model import evaluate, is_fresh, temperature_celsius
from .power import read_power

LOGGER = logging.getLogger(__name__)


class SolarClimateCoordinator(DataUpdateCoordinator):
    """Separate runtime state for each selected climate entity."""

    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry, always_update=False)
        self.entry = entry
        self.settings = {**DEFAULTS, **entry.data, **entry.options}
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.demand = False
        self.signature = None

    async def async_initialize(self):
        saved = await self.store.async_load() or {}
        self.signature = self._signature()
        if saved.get("signature") == self.signature:
            self.demand = saved.get("demand") is True
        self.entry.async_on_unload(
            async_track_state_change_event(
                self.hass,
                [self.settings["temperature_entity"], self.settings["climate_entity"]]
                + [self.settings[key] for key in POWER_SOURCES.values() if self.settings.get(key)],
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
        return {"demand": self.demand, "signature": self.signature}

    @callback
    def _state_changed(self, event):
        self._evaluate()

    @callback
    def _tick(self, now):
        self._evaluate()

    @callback
    def _evaluate(self):
        settings = self.settings
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
            self.store.async_delay_save(self._stored_state, 1)
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
                read_power(
                    source.state,
                    source.attributes.get("unit_of_measurement"),
                    now=now,
                    reported=source.last_reported,
                    max_age=settings[
                        "power_max_data_age" if key == "pv_power" else "forecast_max_data_age"
                    ],
                )
                if source
                else None
            )
        if self.data != data:
            if self.data is None or self.data.get("reason") != decision.reason:
                LOGGER.debug("Entry %s: %s", self.entry.entry_id, decision.reason)
            self.async_set_updated_data(data)
