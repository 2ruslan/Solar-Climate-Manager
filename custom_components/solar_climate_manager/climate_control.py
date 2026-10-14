"""Device temperature validation and bounded command acknowledgement matching."""

from math import ceil, floor, isclose, isfinite

from .manual import CONTROL_ATTRIBUTES

ACKNOWLEDGEMENT_SECONDS = 30
COMMAND_TIMEOUT_SECONDS = 10
TARGET_UPDATE_SECONDS = 60
COMPENSATION_RESERVE_C = 1.1


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def temperature_matches(actual, target):
    value = number(actual)
    return value is not None and isclose(value, target, abs_tol=0.05, rel_tol=0)


def compensation_needed(set_temperature, ac_temperature, mode):
    """Refresh only when the device's remaining heating/cooling reserve is small."""
    target, current = number(set_temperature), number(ac_temperature)
    if target is None or current is None:
        return True
    reserve = target - current if mode == "heat" else current - target
    return reserve < COMPENSATION_RESERVE_C and not isclose(
        reserve, COMPENSATION_RESERVE_C, abs_tol=1e-9, rel_tol=0
    )


def normalized_target(target_c, attributes, unit, *, clamp=False, bounds_c=None):
    """Climate state bounds and service temperatures use HA's display unit."""
    target_c = number(target_c)
    if target_c is None:
        raise ValueError("invalid_target")
    features = attributes.get("supported_features")
    if features is not None and not features & 1:  # TARGET_TEMPERATURE
        raise ValueError("unsupported_temperature")
    target = target_c * 9 / 5 + 32 if unit == "°F" else target_c
    minimum = number(attributes.get("min_temp"))
    maximum = number(attributes.get("max_temp"))
    origin = minimum if minimum is not None else 0
    if bounds_c is not None:
        lower, upper = (number(value) for value in bounds_c)
        if lower is None or upper is None or lower > upper:
            raise ValueError("invalid_ac_temperature_limits")
        if unit == "°F":
            lower, upper = lower * 1.8 + 32, upper * 1.8 + 32
        minimum = max(lower, minimum) if minimum is not None else lower
        maximum = min(upper, maximum) if maximum is not None else upper
        if minimum > maximum:
            raise ValueError("invalid_ac_temperature_limits")
    if clamp:
        if minimum is not None:
            target = max(minimum, target)
        if maximum is not None:
            target = min(maximum, target)
    elif (minimum is not None and target < minimum) or (maximum is not None and target > maximum):
        raise ValueError("invalid_target")
    step = number(attributes.get("target_temp_step"))
    if step is not None and step > 0:
        if bounds_c is not None:
            first = ceil((minimum - origin) / step - 1e-9)
            last = floor((maximum - origin) / step + 1e-9)
            if first > last:
                raise ValueError("invalid_ac_temperature_limits")
            index = min(last, max(first, floor((target - origin) / step + 0.5)))
            return round(origin + index * step, 6)
        target = origin + floor((target - origin) / step + 0.5) * step
        if minimum is not None:
            target = max(minimum, target)
        if maximum is not None:
            target = min(maximum, target)
    return round(target, 6)


def acknowledgement_changes(old, new):
    changes = {}
    if old.state != new.state:
        changes["hvac_mode"] = new.state
    for key in CONTROL_ATTRIBUTES:
        if old.attributes.get(key) != new.attributes.get(key):
            changes[key] = new.attributes.get(key)
    return changes


def matches_acknowledgement(changes, expected):
    """Match only pending commanded fields, not a blanket grace period."""
    return bool(changes) and all(
        key in expected
        and (
            temperature_matches(value, expected[key])
            if key == "temperature"
            else value == expected[key]
        )
        for key, value in changes.items()
    )


def compensated_target(room_target, room_temperature, ac_temperature):
    """Preserve the room's temperature error at the device's own thermostat."""
    readings = tuple(number(value) for value in (room_target, room_temperature, ac_temperature))
    if any(value is None for value in readings):
        return None
    target, room, ac = readings
    return target + ac - room
