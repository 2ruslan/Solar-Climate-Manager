"""Pure validation of measured power; never infer available surplus."""

from math import isfinite


def power_watts(value, unit):
    """Power only: energy in Wh/kWh cannot be substituted for a power measurement."""
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


def signed_power_watts(value, unit):
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
    return round(result, 1) if isfinite(result) else None


def soc_percent(value, unit):
    if unit != "%" or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and 0 <= result <= 100 else None
