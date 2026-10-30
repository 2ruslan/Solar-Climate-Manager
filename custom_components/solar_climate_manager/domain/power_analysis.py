"""Passive, bounded profiles from isolated cycles bracketed by quiet baselines.

These are aggregate-load estimates, never measurements or allocation inputs.
"""

from copy import deepcopy
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
class AdaptiveAnalysis:
    """Minute observations with uncertain background, never control inputs."""

    background: list[tuple[float, float]] = field(default_factory=list)
    evidence: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    status: str = "waiting_background"
    last_report: float | None = None
    active: str | None = None
    since: float | None = None
    condition: Conditions | None = None
    window: list[tuple[float, float]] = field(default_factory=list)

    def reset(self, status: str) -> None:
        self.active = self.since = self.condition = None
        self.window.clear()
        self.status = status

    def prune(self, now: float) -> None:
        self.background = [(t, v) for t, v in self.background if 0 <= now-t <= 86400][-2880:]
        self.evidence = {k: [r for r in rows if 0 <= now-r["time"] <= RETENTION][-2000:]
                         for k, rows in self.evidence.items()}

    def observe(self, now: float, reported: float | None, watts: float | None,
                members: dict[str, Conditions | None], valid: bool,
                historical: bool = False) -> None:
        self.prune(now)
        if (not valid or not numeric(reported) or reported is None
                or not 0 <= now-reported <= (86400 if historical else 90)
                or not numeric(watts) or watts is None or watts < 0):
            self.reset("invalid_data")
            return
        if self.last_report is not None and reported-self.last_report < 60:
            return
        seconds = min(60, max(0, reported-self.last_report)) if self.last_report is not None else 0
        if self.last_report is not None and reported-self.last_report > 90:
            seconds = 0
            self.window.clear()
        self.last_report = reported
        running = {k: v for k, v in members.items() if v is not None}
        if not running:
            if not any(t == reported for t, _ in self.background):
                self.background.append((reported, watts))
            self.window.clear()
            self.active = None
            self.status = "ready"
            return
        # Smooth short spikes only across the same active membership. Temperature
        # drift is evidence, not a reason to discard the last ten minutes.
        active = "|".join(sorted(running))
        if self.active != active:
            self.window.clear()
        self.active = active
        self.window.append((reported, watts))
        self.window = self.window[-5:]
        total = median(v for _, v in self.window)
        background = [(t, v) for t, v in self.background if 0 <= now-t <= 86400]
        base = sorted(v for _, v in background)
        known_background = len(base) >= 3
        low_base = base[int((len(base)-1)*.1)] if known_background else 0
        high_base = base[min(len(base)-1, int((len(base)-1)*.9+.999))] if known_background else total
        age = max(0, now-max(t for t, _ in background))/3600 if background else 24
        margin = 100 + age*25
        for device, condition in running.items():
            assert condition is not None
            # Simultaneous appliances are not identifiable without independent
            # evidence. Retain broad bounds instead of inventing an equal split.
            identified = known_background and len(running) == 1
            low = max(0, total-high_base-margin) if identified else 0
            high = max(low, total-low_base+margin) if identified else total+margin
            high = min(10000, high)
            low = min(low, high)
            rows = self.evidence.setdefault(device, [])
            if not rows or rows[-1]["time"] < reported:
                rows.append({"time": reported, "conditions": asdict(condition),
                             "low": round(low, 1), "high": round(high, 1),
                             "seconds": seconds, "identified": identified})
                self.evidence[device] = rows[-2000:]
        self.status = "interval_ready" if known_background and len(running) == 1 else "rough_interval"

    def aggregate(self, rows: list[dict[str, Any]], now: float) -> dict[str, Any]:
        independent = [r for r in rows if r.get("identified", True)]
        recent = sorted(independent or rows, key=lambda r: r["time"])[-120:]
        centers = sorted((r["low"]+r["high"])/2 for r in recent)
        n = len(recent)
        # Repetition shrinks startup uncertainty, not the unexplained background range.
        half = median((r["high"]-r["low"])/2 for r in recent) + 150/(n**.5)
        half += min(1000, max(0, now-recent[-1]["time"])/86400*100)
        low = max(0, centers[int((n-1)*.1)]-half)
        high = centers[min(n-1, int((n-1)*.9+.999))]+half
        if not independent:
            low = 0
        return {"low": round(low, 1), "high": round(high, 1), "windows": n,
                "minutes": sum(r["seconds"] for r in recent)/60,
                "updated_at": recent[-1]["time"],
                "confidence": "provisional" if independent else "rough"}

    def view(self, device: str, condition: Conditions | None, now: float) -> dict[str, Any]:
        self.prune(now)
        rows = self.evidence.get(device, [])
        buckets: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in rows:
            buckets.setdefault(Conditions(**row["conditions"]).bucket(), []).append(row)
        profiles = [{"conditions": values[-1]["conditions"], **self.aggregate(values, now)}
                    for values in buckets.values()]
        profiles.sort(key=lambda r: r["updated_at"], reverse=True)
        matches = [r for r in rows if condition and condition.similar(Conditions(**r["conditions"]))]
        result = self.aggregate(matches, now) if matches else {
            "low": None, "high": None, "windows": 0, "minutes": 0,
            "updated_at": None, "confidence": "insufficient"}
        # Soft monotonicity: contradictions expand uncertainty; never fabricate a
        # strict physical law or tighten a bound from a neighbouring temperature.
        if matches and condition:
            for row in profiles:
                other = Conditions(**row["conditions"])
                if condition.similar(other):
                    if other.delta < condition.delta:
                        result["high"] = max(result["high"], row["high"])
                    elif other.delta > condition.delta:
                        result["low"] = min(result["low"], row["low"])
        return {**result, "profiles": profiles[:100], "status": self.status,
                "background_samples": len(self.background),
                "warmup_remaining": max(0, 600-(now-self.since)) if self.since is not None else None}

    def stored(self) -> dict[str, Any]:
        return deepcopy({"background": [], "evidence": self.evidence, "last_report": self.last_report})

    @classmethod
    def restore(cls, data: Any, now: float) -> "AdaptiveAnalysis":
        result = cls()
        if not isinstance(data, dict):
            return result
        background = data.get("background", [])
        if isinstance(background, list):
            result.background = [(p[0], p[1]) for p in background[-2880:]
                                 if isinstance(p, (list, tuple)) and len(p) == 2
                                 and all(numeric(v) for v in p) and 0 <= p[0] <= now and p[1] >= 0]
        evidence = data.get("evidence", {})
        if isinstance(evidence, dict):
            for device, rows in list(evidence.items())[:100]:
                if not isinstance(device, str) or not isinstance(rows, list):
                    continue
                for row in rows[-2000:]:
                    if not isinstance(row, dict):
                        continue
                    c = row.get("conditions")
                    if (not all(numeric(row.get(k)) for k in ("time", "low", "high", "seconds"))
                            or not 0 <= row["time"] <= now or not 0 <= row["low"] <= row["high"] <= 10000
                            or not 0 <= row["seconds"] <= 300 or not isinstance(c, dict)
                            or not isinstance(row.get("identified", True), bool)
                            or set(c) != {"mode", "fan", "indoor", "target", "outdoor", "phase"}
                            or c["mode"] not in ("heat", "cool") or not isinstance(c["fan"], str)
                            or len(c["fan"]) > 100 or c["phase"] != "steady"
                            or not all(numeric(c.get(k)) for k in ("indoor", "target"))
                            or c["outdoor"] is not None and not numeric(c["outdoor"])):
                        continue
                    result.evidence.setdefault(device, []).append(deepcopy(row))
        result.prune(now)
        stamp = data.get("last_report")
        if stamp is not None and numeric(stamp) and 0 <= stamp <= now:
            result.last_report = stamp
        return result


@dataclass
class GroupAnalysis:
    context: str = ""
    background: list[tuple[float, float]] = field(default_factory=list)
    profiles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    status: str = "waiting_background"
    rejected_cycles: int = 0
    adaptive: AdaptiveAnalysis = field(default_factory=AdaptiveAnalysis)
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
                members: dict[str, Conditions | None], valid: bool = True,
                adaptive: bool = True) -> None:
        if adaptive:
            self.adaptive.observe(now, reported, watts, members, valid)
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
        return {"adaptive": self.adaptive.view(device, condition, now),
                "watts": round(center, 1) if center is not None else None,
                "low": values[max(0, int((count - 1) * .1))] if enough else None,
                "high": values[min(count - 1, int((count - 1) * .9 + .999))] if enough else None,
                "confidence": "moderate" if consistent and count >= 5 else "low" if enough else "insufficient",
                "matching_cycles": count, "cycles": len({r["cycle"] for r in rows}),
                "samples": len(rows), "updated_at": max((r["time"] for r in rows), default=None),
                "conditions": asdict(condition) if condition else None,
                "profiles": rows[-100:], "analysis_only": True,
                "status": self.status, "rejected_cycles": self.rejected_cycles}

    def stored(self) -> dict[str, Any]:
        return {"adaptive": self.adaptive.stored(), "context": self.context, "background": list(self.background),
                "profiles": {k: list(v) for k, v in self.profiles.items()},
                "rejected_cycles": self.rejected_cycles}

    @classmethod
    def restore(cls, data: Any, now: float) -> "GroupAnalysis":
        result = cls()
        if not isinstance(data, dict) or not isinstance(data.get("context"), str):
            return result
        result.context = data["context"]
        result.adaptive = AdaptiveAnalysis.restore(data.get("adaptive"), now)
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
