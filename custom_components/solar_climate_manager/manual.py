"""Conservative external-change detection with local-date pause."""

from collections.abc import Mapping
from datetime import date
from typing import Any

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


def control_fingerprint(state: str, attributes: Mapping[str, Any]) -> tuple[Any, ...] | None:
    if state in ("unknown", "unavailable"):
        return None
    return (state, *(attributes.get(key) for key in CONTROL_ATTRIBUTES))


def pause_active(until_date: str | None, today: date) -> bool:
    if until_date is None:
        return False
    try:
        return date.fromisoformat(until_date) >= today
    except (TypeError, ValueError):
        return False
