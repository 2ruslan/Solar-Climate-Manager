"""Read-only observation sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfPower, UnitOfTemperature

from .const import POWER_SOURCES
from .entity import SolarClimateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            SolarClimateSensor(entry.runtime_data, key)
            for key in ("temperature", "reason", "automation_mode", *POWER_SOURCES)
        ]
    )


class SolarClimateSensor(SolarClimateEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif key in POWER_SOURCES:
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
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

    @property
    def available(self):
        if self.key in POWER_SOURCES:
            return super().available and self.coordinator.data.get(self.key) is not None
        return super().available
