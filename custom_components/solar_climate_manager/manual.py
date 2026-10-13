"""Conservative external-change detection; this demo never issues commands."""

from datetime import date

CONTROL_ATTRIBUTES = (
    "temperature",
    "target_temp_low",
    "target_temp_high",
    "fan_mode",
    "preset_mode",
    "swing_mode",
    "swing_horizontal_mode",
    "quiet",
    "xtra_fan",
)


def control_fingerprint(state, attributes):
    if state in ("unknown", "unavailable"):
        return None
    return (state, *(attributes.get(key) for key in CONTROL_ATTRIBUTES))


def pause_active(until_date, today):
    try:
        return date.fromisoformat(until_date) >= today
    except (TypeError, ValueError):
        return False
