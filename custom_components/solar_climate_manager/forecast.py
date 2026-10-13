"""Validate forecast coverage, units and aware timestamps without HA dependencies."""

from datetime import datetime, timedelta, timezone

from .power import power_watts


def aware_datetime(value):
    try:
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(value.replace("Z", "+00:00"))
        )
    except (ValueError, TypeError, AttributeError):
        return None
    return (
        parsed.astimezone(timezone.utc)
        if parsed.tzinfo is not None and parsed.utcoffset() is not None
        else None
    )


def covered_forecast(
    records, *, now, horizon_minutes=60, period_minutes=30, attribute="pv_estimate", unit="kW"
):
    """Return all power samples covering [now, horizon]; gaps/overlaps are invalid."""
    if not isinstance(records, (list, tuple)):
        return None
    end = now + timedelta(minutes=horizon_minutes)
    intervals = []
    for record in records:
        if not isinstance(record, dict):
            return None
        start = aware_datetime(record.get("period_start"))
        finish = (
            aware_datetime(record.get("period_end"))
            if "period_end" in record
            else start + timedelta(minutes=period_minutes)
            if start
            else None
        )
        if start is None or finish is None or finish <= start:
            return None
        if finish <= now or start >= end:
            continue
        value = power_watts(record.get(attribute), unit)
        if value is None:
            return None
        intervals.append((start, finish, value))
    intervals.sort(key=lambda item: item[0])
    cursor = now
    values = []
    previous_end = None
    for start, finish, value in intervals:
        if start > cursor or previous_end is not None and start < previous_end:
            return None
        values.append(value)
        cursor = finish
        previous_end = finish
    return tuple(values) if cursor >= end and values else None
