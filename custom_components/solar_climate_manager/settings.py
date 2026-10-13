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
    "require_forecast",
    "allow_forecast_trial",
    "load_includes_ac",
    "load_includes_battery_charging",
    "grid_on_means_available",
    "pause_on_external_change",
]


def valid_policy(values):
    return values["critical_soc"] < values["minimum_soc"] <= values["battery_reserve_soc"]
