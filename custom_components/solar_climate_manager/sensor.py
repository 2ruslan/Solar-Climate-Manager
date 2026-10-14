"""Read-only observation sensors."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature, UnitOfTime

from .const import POWER_SOURCES
from .entity import SolarClimateEntity
from .settings import OPERATION_MODES
from .strategy import ACTIONS, REASONS

POWER_KEYS = [
    *POWER_SOURCES,
    "load_power",
    "house_load_power",
    "battery_charge_power",
    "battery_power",
    "grid_power",
    "grid_import_limit",
    "grid_import_margin",
    "ac_power",
    "solar_margin",
    "average_solar_margin",
    "forecast_margin",
]
TEMPERATURE_KEYS = [
    "temperature",
    "ac_temperature",
    "temperature_offset",
    "ac_target_temperature",
    "ac_set_temperature",
]
DURATION_KEYS = ["seconds_to_start", "seconds_to_stop"]
ENUM_OPTIONS = {
    "automation_mode": list(OPERATION_MODES),
    "reason": ["invalid_data", "disabled", "temperature_demand", "temperature_satisfied"],
    "strategy_action": ACTIONS,
    "strategy_reason": REASONS,
    "energy_reason": REASONS,
    "command_error": [
        "none", "service_error", "invalid_target", "unsupported_temperature",
        "invalid_ac_temperature_limits",
    ],
    "manual_status": ["automatic", "manual_today", "disabled"],
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            SolarClimateSensor(entry.runtime_data, key)
            for key in (*TEMPERATURE_KEYS, *ENUM_OPTIONS, *POWER_KEYS, *DURATION_KEYS, "soc")
        ]
    )


class SolarClimateSensor(SolarClimateEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in TEMPERATURE_KEYS:
            if key != "temperature_offset":
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
        if self.key in POWER_KEYS or self.key in TEMPERATURE_KEYS or self.key == "soc":
            return super().available and self.coordinator.data.get(self.key) is not None
        return super().available

    @property
    def extra_state_attributes(self):
        if self.key == "strategy_action":
            return {
                "target_temperature_c": self.coordinator.settings["target_temperature"],
                "ac_temperature_c": self.coordinator.data["ac_temperature"],
                "temperature_offset_c": self.coordinator.data["temperature_offset"],
                "ac_target_temperature_c": self.coordinator.data["ac_target_temperature"],
                "ac_set_temperature_c": self.coordinator.data["ac_set_temperature"],
                "ac_min_temperature_c": self.coordinator.settings["ac_min_temperature"],
                "ac_max_temperature_c": self.coordinator.settings["ac_max_temperature"],
                "estimated_ac_power_w": self.coordinator.settings["estimated_ac_power"],
                "manual_until_date": self.coordinator.manual_date,
                "grid_import_limit_w": self.coordinator.data["grid_import_limit"],
                "grid_import_margin_w": self.coordinator.data["grid_import_margin"],
                "grid_import_limit_active": self.coordinator.data["grid_import_limit_active"],
            }
        return None
