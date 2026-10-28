"""Passive, bounded profiles from isolated cycles bracketed by quiet baselines.

These are aggregate-load estimates, never measurements or allocation inputs.
"""

from dataclasses import asdict, dataclass, field
from math import isfinite
from statistics import median
from typing import Any

RETENTION = 30 * 86400
MAX_SAMPLES = 2000
MAX_CYCLE = 6 * 3600


def numeric(value: Any) -> bool:
    return type(value) in (int, float) and isfinite(value)


def quiet(points: list[tuple[float, float]]) -> bool:
    values = [v for _, v in points]
    return (len(points) >= 3 and points[-1][0] - points[0][0] >= 60
            and max(values) - min(values) <= max(80, median(values) * .08))


@dataclass(frozen=True)
class Conditions:
    mode: str
    fan: str
    indoor: float
    target: float
    outdoor: float | None = None
    phase: str = "steady"

    @property
    def delta(self) -> float:
        return self.target - self.indoor if self.mode == "heat" else self.indoor - self.target

    def similar(self, other: "Conditions") -> bool:
        return (self.mode == other.mode and self.fan == other.fan and self.phase == other.phase
                and abs(self.delta - other.delta) <= 2
                and abs(self.indoor - other.indoor) <= 3
                and abs(self.target - other.target) <= 3
                and ((self.outdoor is None and other.outdoor is None)
                     or (self.outdoor is not None and other.outdoor is not None
                         and abs(self.outdoor - other.outdoor) <= 5)))

    def bucket(self) -> tuple[Any, ...]:
        return (self.mode, self.fan, round(self.indoor / 2), round(self.target / 2),
                None if self.outdoor is None else round(self.outdoor / 5), self.phase)


@dataclass
class GroupAnalysis:
    context: str = ""
    background: list[tuple[float, float]] = field(default_factory=list)
    profiles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    status: str = "waiting_background"
    rejected_cycles: int = 0
    # In-flight cycles are deliberately never restored after a gap or restart.
    baseline: list[tuple[float, float]] = field(default_factory=list, repr=False)
    window: list[tuple[float, float]] = field(default_factory=list, repr=False)
    pending: list[tuple[Conditions, float]] = field(default_factory=list, repr=False)
    active: str | None = None
    started: float | None = None
    before: float | None = None
    condition: Conditions | None = None
    condition_since: float | None = None
    last_report: float | None = None
    last_sample: float | None = None
    stopped: bool = False

    def reset_cycle(self) -> None:
        self.baseline.clear()
        self.window.clear()
        self.pending.clear()
        self.active = self.started = self.before = None
        self.condition = self.condition_since = None
        self.stopped = False

    def reject(self, reason: str) -> None:
        if self.active is not None:
            self.rejected_cycles += 1
        self.reset_cycle()
        self.status = reason

    def prune(self, now: float) -> None:
        self.background = [(t, v) for t, v in self.background if 0 <= now - t <= RETENTION][-2048:]
        self.profiles = {key: [s for s in rows if 0 <= now - s["time"] <= RETENTION][-MAX_SAMPLES:]
                         for key, rows in self.profiles.items()}

    def observe(self, *, now: float, reported: float | None, watts: float | None,
                members: dict[str, Conditions | None], valid: bool = True) -> None:
        self.prune(now)
        if (not valid or not numeric(reported) or reported is None
                or not 0 <= now - reported <= 90 or not numeric(watts)
                or watts is None or watts < 0):
            self.reject("invalid_data")
            return
        # Known device transitions invalidate ambiguity even before the house
        # meter reports again. Re-reading a report must not hide an overlap.
        running = {key: value for key, value in members.items() if value is not None}
        if len(running) > 1:
            self.reject("multiple_running")
            return
        if self.active is not None:
            if running and (self.stopped or self.active not in running):
                self.reject("overlapping_cycle")
                return
            if not running and not self.stopped:
                self.baseline.clear()
                self.stopped = True
        if self.last_report is not None and reported <= self.last_report:
            return
        if self.last_report is not None and reported - self.last_report > 90:
            self.reject("data_gap")
        self.last_report = reported
        if self.last_sample is not None and reported - self.last_sample < 30:
            return
        self.last_sample = reported
        if not running:
            self.background.append((reported, watts))
            self.background = self.background[-2048:]
            if self.active is not None and not self.stopped:
                self.baseline.clear()
                self.stopped = True
            self.baseline.append((reported, watts))
            self.baseline = [(t, v) for t, v in self.baseline if reported - t <= 120]
            if quiet(self.baseline):
                after = median(v for _, v in self.baseline)
                if self.active is not None and self.before is not None:
                    if abs(after - self.before) <= max(100, self.before * .15):
                        self._commit(reported, (after + self.before) / 2)
                    else:
                        self.reject("background_changed")
                        return
                    # The ending baseline may also anchor the next cycle.
                    baseline = list(self.baseline)
                    self.reset_cycle()
                    self.baseline = baseline
                self.status = "ready"
            else:
                self.status = "checking_background" if self.stopped else "waiting_background"
            if self.started is not None and reported - self.started > MAX_CYCLE:
                self.reject("cycle_too_long")
            return
        device, condition = next(iter(running.items()))
        assert condition is not None
        if self.stopped or self.active is not None and self.active != device:
            self.reject("overlapping_cycle")
            return
        if self.active is None:
            if not quiet(self.baseline) or reported - self.baseline[-1][0] > 90:
                self.reject("waiting_background")
                return
            self.active, self.started = device, reported
            self.before = median(v for _, v in self.baseline)
            self.baseline.clear()
        assert self.started is not None
        if reported - self.started > MAX_CYCLE:
            self.reject("cycle_too_long")
            return
        phase = "startup" if reported - self.started < 600 else "steady"
        condition = Conditions(condition.mode, condition.fan, condition.indoor,
                               condition.target, condition.outdoor, phase)
        # Setpoint/fan changes restart settling; drifting indoor readings do not.
        changed = (self.condition is None or self.condition.mode != condition.mode
                   or self.condition.fan != condition.fan or self.condition.target != condition.target
                   or self.condition.phase != condition.phase)
        if changed:
            self.window.clear()
            self.condition_since = reported
        self.condition = condition
        assert self.condition_since is not None
        if reported - self.condition_since < 120:
            self.status = "settling"
            return
        self.window.append((reported, watts))
        self.window = [(t, v) for t, v in self.window if reported - t <= 90]
        self.status = "collecting"
        if quiet(self.window):
            self.pending.append((condition, median(v for _, v in self.window)))
            self.pending = self.pending[-720:]
            self.window.clear()

    def _commit(self, now: float, background: float) -> None:
        assert self.active is not None and self.started is not None
        buckets: dict[tuple[Any, ...], list[tuple[Conditions, float]]] = {}
        for condition, total in self.pending:
            delta = total - background
            if -50 <= delta <= 10000:
                buckets.setdefault(condition.bucket(), []).append((condition, max(0, delta)))
        rows = self.profiles.setdefault(self.active, [])
        for values in buckets.values():
            rows.append({"time": now, "cycle": self.started,
                         "conditions": asdict(values[-1][0]),
                         "watts": round(median(v for _, v in values), 1)})
        self.profiles[self.active] = rows[-MAX_SAMPLES:]

    def estimate(self, device: str, condition: Conditions | None, now: float) -> dict[str, Any]:
        self.prune(now)
        rows = self.profiles.get(device, [])
        matches: dict[float, list[float]] = {}
        if condition is not None:
            for row in rows:
                if condition.similar(Conditions(**row["conditions"])):
                    matches.setdefault(row["cycle"], []).append(row["watts"])
        values = sorted(float(median(v)) for v in matches.values())
        count = len(values)
        enough = count >= 3
        center = float(median(values)) if enough else None
        spread = values[-1] - values[0] if enough else None
        consistent = enough and spread is not None and center is not None and spread <= max(150, center * .5)
        return {"watts": round(center, 1) if center is not None else None,
                "low": values[max(0, int((count - 1) * .1))] if enough else None,
                "high": values[min(count - 1, int((count - 1) * .9 + .999))] if enough else None,
                "confidence": "moderate" if consistent and count >= 5 else "low" if enough else "insufficient",
                "matching_cycles": count, "cycles": len({r["cycle"] for r in rows}),
                "samples": len(rows), "updated_at": max((r["time"] for r in rows), default=None),
                "conditions": asdict(condition) if condition else None,
                "profiles": rows[-100:], "analysis_only": True,
                "status": self.status, "rejected_cycles": self.rejected_cycles}

    def stored(self) -> dict[str, Any]:
        return {"context": self.context, "background": list(self.background),
                "profiles": {k: list(v) for k, v in self.profiles.items()},
                "rejected_cycles": self.rejected_cycles}

    @classmethod
    def restore(cls, data: Any, now: float) -> "GroupAnalysis":
        result = cls()
        if not isinstance(data, dict) or not isinstance(data.get("context"), str):
            return result
        result.context = data["context"]
        background = data.get("background", [])
        if isinstance(background, list):
            for point in background[-2048:]:
                if (isinstance(point, (list, tuple)) and len(point) == 2
                        and all(numeric(v) for v in point) and 0 <= now - point[0] <= RETENTION
                        and point[1] >= 0):
                    result.background.append((point[0], point[1]))
        profiles = data.get("profiles", {})
        if isinstance(profiles, dict):
            for device, rows in list(profiles.items())[:100]:
                if not isinstance(device, str) or not isinstance(rows, list):
                    continue
                accepted = []
                for row in rows[-MAX_SAMPLES:]:
                    if not isinstance(row, dict):
                        continue
                    c = row.get("conditions")
                    if (not all(numeric(row.get(k)) for k in ("time", "cycle", "watts"))
                            or not 0 <= row["cycle"] <= row["time"] <= now
                            or not 0 <= row["watts"] <= 10000 or not isinstance(c, dict)
                            or set(c) != {"mode", "fan", "indoor", "target", "outdoor", "phase"}
                            or c["mode"] not in ("heat", "cool") or not isinstance(c["fan"], str)
                            or len(c["fan"]) > 100 or c["phase"] not in ("startup", "steady")
                            or not all(numeric(c.get(k)) for k in ("indoor", "target"))
                            or (c["outdoor"] is not None and not numeric(c["outdoor"]))):
                        continue
                    accepted.append({k: row[k] for k in ("time", "cycle", "watts", "conditions")})
                result.profiles[device] = accepted
        rejected = data.get("rejected_cycles", 0)
        result.rejected_cycles = rejected if type(rejected) is int and rejected >= 0 else 0
        result.prune(now)
        return result
