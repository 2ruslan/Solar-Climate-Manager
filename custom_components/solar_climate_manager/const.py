"""Shared integration constants."""

from homeassistant.const import Platform

from .settings import RETIRED_RULES
from .strategy import STRATEGY_DEFAULTS

DOMAIN = "solar_climate_manager"
POWER_SOURCES = {
    "pv_power": "pv_power_entity",
    "forecast_power_now": "forecast_power_now_entity",
    "forecast_power_30m": "forecast_power_30m_entity",
    "forecast_power_60m": "forecast_power_60m_entity",
}
ENERGY_SOURCES = {
    "load_power": "load_power_entity",
    "battery_power": "battery_power_entity",
    "grid_power": "grid_power_entity",
    "soc": "soc_entity",
    "grid_available": "grid_available_entity",
    "ac_power": "ac_power_entity",
    "schedule_allowed": "schedule_entity",
}
OPTIONAL_SOURCES = [
    *POWER_SOURCES.values(),
    *ENERGY_SOURCES.values(),
]
REMOVED_FORECAST_SETTINGS = {
    "forecast_detail_entity",
    "forecast_updated_entity",
    "forecast_max_data_age",
    "forecast_detail_attribute",
    "forecast_value_attribute",
    "forecast_detail_unit",
    "forecast_generation_max_age",
    "forecast_period_minutes",
    "forecast_horizon",
}
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]
REMOVED_SETTINGS = REMOVED_FORECAST_SETTINGS | {"battery_charge_power_entity"} | RETIRED_RULES
DEFAULTS = {
    **STRATEGY_DEFAULTS,
    "target_temperature": 23.0,
    "hysteresis": 1.0,
    "hvac_mode": "heat",
    "max_data_age": 900,
    "enabled": True,
    "power_max_data_age": 900,
}
