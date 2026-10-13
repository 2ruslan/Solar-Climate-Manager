"""UI metadata for demo policy parameters."""

# key: min, max, step, unit
NUMERIC_SETTINGS = {
    "estimated_ac_power": (100, 10000, 50, "W"),
    "power_reserve": (0, 10000, 50, "W"),
    "energy_hysteresis": (0, 5000, 50, "W"),
    "minimum_soc": (0, 100, 1, "%"),
    "critical_soc": (0, 100, 1, "%"),
    "battery_reserve_soc": (0, 100, 1, "%"),
    "charging_reserve_power": (0, 10000, 50, "W"),
    "max_battery_discharge": (0, 10000, 50, "W"),
    "max_grid_import": (0, 20000, 50, "W"),
    "start_delay": (0, 7200, 30, "s"),
    "shortage_delay": (0, 7200, 30, "s"),
    "grid_absence_delay": (0, 7200, 30, "s"),
    "minimum_run_time": (0, 7200, 30, "s"),
    "minimum_off_time": (0, 7200, 30, "s"),
    "verification_delay": (0, 1800, 30, "s"),
    "adverse_power_delay": (0, 1800, 30, "s"),
    "grid_max_data_age": (30, 604800, 30, "s"),
}
BOOLEAN_SETTINGS = [
    "prioritize_charging",
    "allow_grid_import",
    "load_includes_ac",
    "load_includes_battery_charging",
    "grid_on_means_available",
]

ADVANCED_KEYS = {
    "max_data_age",
    "power_max_data_age",
    "grid_max_data_age",
    "energy_hysteresis",
    "verification_delay",
    "adverse_power_delay",
    "max_battery_discharge",
    "start_delay",
    "shortage_delay",
    "grid_absence_delay",
    "minimum_run_time",
    "minimum_off_time",
}
COMFORT_KEYS = {
    "temperature_entity",
    "target_temperature",
    "hysteresis",
    "hvac_mode",
    "schedule_entity",
}
ENERGY_KEYS = {
    "estimated_ac_power",
    "power_reserve",
    "minimum_soc",
    "critical_soc",
    "battery_reserve_soc",
    "prioritize_charging",
    "allow_grid_import",
}
SOURCE_FLAGS = {
    "load_includes_ac",
    "load_includes_battery_charging",
    "grid_on_means_available",
    "battery_positive",
    "grid_positive",
}
RETIRED_RULES = {"require_forecast", "allow_forecast_trial", "pause_on_external_change"}


def merge_section(values, updates, *, clear_sources=(), removed=()):
    """Editing one section must preserve every other section and enabled state."""
    merged = {key: value for key, value in values.items() if key not in removed}
    merged.update(updates)
    for key in clear_sources:
        merged[key] = updates.get(key)
    return merged


def valid_policy(values):
    return values["critical_soc"] < values["minimum_soc"] <= values["battery_reserve_soc"]
