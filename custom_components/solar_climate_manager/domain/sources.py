"""Normalized inputs captured once for a single synchronous evaluation."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .types import EnergySnapshot

SourceStatus = Literal[
    "valid", "not_configured", "missing", "unavailable", "stale", "future", "invalid"
]


@dataclass(frozen=True)
class SourceReading:
    value: float | bool | str | None
    reported_at: datetime | None
    status: SourceStatus


@dataclass(frozen=True)
class SourceSnapshot:
    captured_at: datetime
    readings: Mapping[str, SourceReading]
    values: Mapping[str, float | bool | None]
    temperature: float | None
    ac_temperature: float | None
    ac_set_temperature: float | None
    ac_target_temperature: float | None
    climate_valid: bool
    running: bool | None
    energy: EnergySnapshot
