"""Pure validation of actual and forecast power; never infer available surplus."""

from datetime import datetime
from math import isfinite

from .model import is_fresh


def power_watts(value, unit):
    """Power only: energy in Wh/kWh cannot be substituted for a power forecast."""
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if unit == "kW":
        result *= 1000
    elif unit != "W":
        return None
    return result if isfinite(result) and result >= 0 else None


def read_power(value, unit, *, now: datetime, reported: datetime, max_age: float):
    """Missing, stale and future data are unknown, rather than zero generation."""
    if not is_fresh(now, reported, max_age):
        return None
    result = power_watts(value, unit)
    return round(result, 1) if result is not None else None
