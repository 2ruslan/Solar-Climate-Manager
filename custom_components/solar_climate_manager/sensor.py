"""Read-only observation sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import UnitOfTemperature

from .entity import SolarClimateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            SolarClimateSensor(entry.runtime_data, key)
            for key in ("temperature", "reason", "automation_mode")
        ]
    )


class SolarClimateSensor(SolarClimateEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        else:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = (
                ["observation", "disabled"]
                if key == "automation_mode"
                else ["invalid_data", "disabled", "temperature_demand", "temperature_satisfied"]
            )

    @property
    def native_value(self):
        return self.coordinator.data[self.key]
