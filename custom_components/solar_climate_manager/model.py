"""Pure, conservative thermostat; no Home Assistant or device side effects."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class Decision:
    demand: bool
    data_valid: bool
    reason: str


def temperature_celsius(value: str, unit: str | None) -> float | None:
    """Reject unknown units, missing readings and non-finite values."""
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(temperature):
        return None
    if unit == "°F":
        temperature = (temperature - 32) * 5 / 9
    elif unit != "°C":
        return None
    return temperature if -100 <= temperature <= 100 else None


def evaluate(
    temperature: float | None,
    *,
    target: float,
    hysteresis: float,
    mode: str,
    previous_demand: bool,
    enabled: bool = True,
    climate_valid: bool = True,
) -> Decision:
    """Strict thresholds retain the previous decision at the boundaries."""
    if (
        mode not in ("heat", "cool")
        or not isfinite(target)
        or not isfinite(hysteresis)
        or hysteresis <= 0
    ):
        raise ValueError("Invalid thermostat configuration")
    if temperature is None or not isfinite(temperature) or not climate_valid:
        return Decision(False, False, "invalid_data")
    if not enabled:
        return Decision(False, True, "disabled")
    demand = previous_demand
    if mode == "heat":
        if temperature < target - hysteresis:
            demand = True
        elif temperature > target + hysteresis:
            demand = False
    else:
        if temperature > target + hysteresis:
            demand = True
        elif temperature < target - hysteresis:
            demand = False
    return Decision(demand, True, "temperature_demand" if demand else "temperature_satisfied")


def is_fresh(now: datetime, reported: datetime, max_age: float) -> bool:
    """Future timestamps do not establish valid data."""
    age = (now - reported).total_seconds()
    return 0 <= age <= max_age
