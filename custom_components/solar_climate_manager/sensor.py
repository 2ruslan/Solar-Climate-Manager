"""Read-only observation sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature, UnitOfTime

from .const import POWER_SOURCES
from .entity import SolarClimateEntity
from .strategy import ACTIONS, REASONS

POWER_KEYS = [
    *POWER_SOURCES,
    "load_power",
    "house_load_power",
    "battery_charge_power",
    "battery_power",
    "grid_power",
    "ac_power",
    "solar_margin",
    "forecast_margin",
]
DURATION_KEYS = ["seconds_to_start", "seconds_to_stop"]
ENUM_OPTIONS = {
    "automation_mode": ["observation", "disabled"],
    "reason": ["invalid_data", "disabled", "temperature_demand", "temperature_satisfied"],
    "demo_action": ACTIONS,
    "strategy_reason": REASONS,
    "manual_status": ["automatic", "manual_today", "disabled"],
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            SolarClimateSensor(entry.runtime_data, key)
            for key in ("temperature", *ENUM_OPTIONS, *POWER_KEYS, *DURATION_KEYS, "soc")
        ]
    )


class SolarClimateSensor(SolarClimateEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif key in POWER_KEYS:
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_native_unit_of_measurement = UnitOfPower.WATT
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 0
        elif key in DURATION_KEYS:
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.SECONDS
        elif key == "soc":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = PERCENTAGE
        else:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = ENUM_OPTIONS[key]

    @property
    def native_value(self):
        return self.coordinator.data[self.key]

    @property
    def available(self):
        if self.key in POWER_KEYS or self.key == "soc":
            return super().available and self.coordinator.data.get(self.key) is not None
        return super().available

    @property
    def extra_state_attributes(self):
        if self.key == "demo_action":
            return {
                "demo_only": True,
                "target_temperature_c": self.coordinator.settings["target_temperature"],
                "estimated_ac_power_w": self.coordinator.settings["estimated_ac_power"],
                "manual_until_date": self.coordinator.manual_date,
            }
        return None
