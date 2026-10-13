"""Shared integration constants."""

from homeassistant.const import Platform

DOMAIN = "solar_climate_manager"
POWER_SOURCES = {
    "pv_power": "pv_power_entity",
    "forecast_power_now": "forecast_power_now_entity",
    "forecast_power_30m": "forecast_power_30m_entity",
    "forecast_power_60m": "forecast_power_60m_entity",
}
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]
DEFAULTS = {
    "target_temperature": 23.0,
    "hysteresis": 1.0,
    "hvac_mode": "heat",
    "max_data_age": 900,
    "enabled": True,
    "power_max_data_age": 900,
    "forecast_max_data_age": 1800,
}
