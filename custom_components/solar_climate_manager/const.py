"""Shared integration constants."""

from homeassistant.const import Platform

DOMAIN = "solar_climate_manager"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]
DEFAULTS = {
    "target_temperature": 23.0,
    "hysteresis": 1.0,
    "hvac_mode": "heat",
    "max_data_age": 900,
    "enabled": True,
}
