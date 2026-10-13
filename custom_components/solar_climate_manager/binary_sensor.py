"""Demand, data health and conservative permission diagnostics."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import SolarClimateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            SolarClimateBinarySensor(entry.runtime_data, key)
            for key in ("demand", "invalid_data", "control_allowed")
        ]
    )


class SolarClimateBinarySensor(SolarClimateEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return self.coordinator.data[self.key]
