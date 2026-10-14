"""UI metadata for control policy parameters."""

OPERATION_MODES = ("disabled", "observation", "control", "temporary_block")
BASE_MODES = OPERATION_MODES[:3]

# key: min, max, step, unit
NUMERIC_SETTINGS = {
    "estimated_ac_power": (100, 10000, 50, "W"),
    "minimum_soc": (0, 100, 1, "%"),
    "grid_absence_minutes": (0, 120, 1, "min"),
}
BOOLEAN_SETTINGS = [
    "load_includes_ac",
    "load_includes_battery_charging",
    "grid_on_means_available",
]

ADVANCED_KEYS = {"grid_absence_minutes"}
FIXED_POLICY_KEYS = {
    "power_max_data_age",
    "grid_max_data_age",
    "max_battery_discharge",
    "start_delay",
    "shortage_delay",
    "minimum_run_time",
    "minimum_off_time",
}


def configuration_values(data, options, defaults, removed):
    saved = {**data, **options}
    values = {key: value for key, value in {**defaults, **saved}.items() if key not in removed}
    for key in FIXED_POLICY_KEYS:
        values[key] = defaults[key]
    minutes = saved.get(
        "grid_absence_minutes", saved.get("grid_absence_delay", defaults["grid_absence_delay"]) / 60
    )
    values["grid_absence_minutes"] = minutes
    values["grid_absence_delay"] = minutes * 60
    mode = saved.get("operation_mode", "observation" if saved.get("enabled", True) else "disabled")
    values["operation_mode"] = (
        mode if mode in OPERATION_MODES else "disabled"
    )
    values.pop("enabled", None)
    return values


COMFORT_KEYS = {
    "temperature_entity",
    "target_temperature",
    "hysteresis",
    "hvac_mode",
    "schedule_entity",
}
ENERGY_KEYS = {
    "estimated_ac_power",
    "minimum_soc",
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
    return 0 <= values["minimum_soc"] <= 100
