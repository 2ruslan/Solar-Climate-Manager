"""Build public entity and export data without making control decisions."""

from typing import Any

from .domain.sources import SourceSnapshot
from .domain.types import PolicyState, StrategyDecision
from .model import Decision


def build_state(
    sources: SourceSnapshot,
    decision: Decision,
    strategy: StrategyDecision,
    policy: PolicyState,
    *,
    operation_mode: str,
    manual: bool,
    command_error: str,
    control_allowed: bool,
) -> dict[str, Any]:
    temperature = sources.temperature
    ac_temperature = sources.ac_temperature
    ac_target = sources.ac_target_temperature
    climate_available = sources.running is not None
    actual_running = sources.running
    grid = sources.energy.grid
    limit_active = sources.energy.grid_limit_configured
    ac_valid = sources.energy.ac_power_valid
    data: dict[str, Any] = {
        "temperature": temperature,
        "ac_temperature": ac_temperature,
        "ac_set_temperature": sources.ac_set_temperature,
        "temperature_offset": (ac_temperature - temperature)
        if ac_temperature is not None and temperature is not None
        else None,
        "ac_target_temperature": ac_target,
        "demand": decision.demand,
        "invalid_data": not decision.data_valid,
        "reason": decision.reason,
        "automation_mode": operation_mode,
        "control_allowed": control_allowed,
        "command_error": command_error,
        "command_failed": command_error != "none",
    }
    data.update(sources.values)
    data.update(
        {
            "grid_available": grid,
            "energy_allowed": strategy.energy_allowed,
            "soc_blocked": policy.soc_blocked,
            "energy_reason": strategy.energy_reason,
            "grid_import_margin": strategy.grid_import_margin,
            "running": actual_running if climate_available else None,
            "strategy_action": strategy.action,
            "strategy_reason": strategy.reason,
            "solar_margin": strategy.solar_margin,
            "average_solar_margin": strategy.average_solar_margin,
            "forecast_margin": strategy.forecast_margin,
            "seconds_to_start": round(strategy.seconds_to_start)
            if strategy.seconds_to_start is not None
            else None,
            "seconds_to_stop": round(strategy.seconds_to_stop)
            if strategy.seconds_to_stop is not None
            else None,
            "manual_pause": manual,
            "manual_status": "disabled"
            if operation_mode == "disabled"
            else "manual_today"
            if manual
            else "automatic",
            "energy_data_invalid": (
                grid is True
                and limit_active
                and (data["grid_import_limit"] is None or data["grid_power"] is None)
            )
            or any(
                value is None
                for value in (
                    data["soc"],
                    data["battery_power"],
                    grid,
                )
            )
            or (
                grid is False
                and (data["pv_power"] is None or data["load_power"] is None or not ac_valid)
            ),
        }
    )
    return data


def build_export(
    settings: dict[str, Any],
    data: dict[str, Any] | None,
    manual_date: str | None,
    previous_mode: str | None,
) -> dict[str, Any]:
    return {
        "version": "0.8.1",
        "settings": {key: value for key, value in settings.items() if not key.endswith("_entity")},
        "decision": {key: value for key, value in data.items() if key != "group_name"} if data is not None else None,
        "manual_until_date": manual_date,
        "mode_after_temporary_block": previous_mode,
    }
