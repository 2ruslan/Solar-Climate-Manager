"""Conservative aggregate-load learning; no HA APIs or command authority."""

from dataclasses import dataclass, field
from math import isfinite
from statistics import median
from typing import Any

MAX_AGE = 30 * 86400


def number(value: Any) -> bool:
    return type(value) in (int, float) and isfinite(value)


def stable(points: list[tuple[float, float]]) -> bool:
    values = [v for _, v in points]
    return bool(values) and max(values) - min(values) <= max(50, median(values) * 0.05)


@dataclass
class PowerLearning:
    context: str = ""
    samples: list[float] = field(default_factory=list)
    updated_at: float | None = None
    status: str = "waiting_baseline"
    baseline: list[tuple[float, float]] = field(default_factory=list, repr=False)
    after: list[tuple[float, float]] = field(default_factory=list, repr=False)
    started: float | None = None
    before_watts: float | None = None
    last_report: float | None = None
    was_running: bool | None = None
    cycle_key: str | None = None

    def bind(self, context: str) -> None:
        if self.context != context:
            self.__dict__.update(PowerLearning(context=context).__dict__)

    def stored(self) -> dict[str, Any]:
        # Never restore an in-flight observation across downtime.
        return {
            "version": 1,
            "context": self.context,
            "samples": list(self.samples),
            "updated_at": self.updated_at,
        }

    def restore(self, data: Any, now: float) -> None:
        if not isinstance(data, dict) or data.get("version") != 1:
            return
        samples, stamp = data.get("samples"), data.get("updated_at")
        if (
            not isinstance(data.get("context"), str)
            or not isinstance(samples, list)
            or len(samples) > 5
            or not all(number(v) and 100 <= v <= 10000 for v in samples)
            or stamp is None
            or not number(stamp)
            or not 0 <= now - stamp <= MAX_AGE
        ):
            return
        self.context = data["context"]
        self.samples = list(samples)
        self.updated_at = stamp

    def learned(self, now: float) -> float | None:
        if (
            len(self.samples) < 3
            or self.updated_at is None
            or not 0 <= now - self.updated_at <= MAX_AGE
        ):
            return None
        if max(self.samples) - min(self.samples) > median(self.samples) * 0.2:
            return None
        return max(self.samples)

    def effective(self, configured: float, now: float) -> float:
        return max(configured, self.learned(now) or configured)

    def reject(self, status: str) -> None:
        self.status = status
        self.baseline.clear()
        self.after.clear()
        self.started = self.before_watts = None

    def observe(
        self,
        *,
        now: float,
        reported: float | None,
        watts: float | None,
        running: bool | None,
        changed: float | None,
        confirmed: float | None,
        eligible: bool,
        settle: float,
        cycle_key: str,
    ) -> None:
        if self.updated_at is not None and not 0 <= now - self.updated_at <= MAX_AGE:
            self.samples.clear()
            self.updated_at = None
        previous = self.was_running
        self.was_running = running
        if not eligible:
            self.reject("ineligible")
            return
        if (
            not number(watts)
            or watts is None
            or watts < 0
            or reported is None
            or not number(reported)
            or not 0 <= now - reported <= 90
            or (self.last_report is not None and reported < self.last_report)
        ):
            self.reject("stale_data")
            return
        fresh = self.last_report is None or reported > self.last_report
        if fresh:
            if self.last_report is not None and reported - self.last_report > 90:
                self.reject("stale_data")
            self.last_report = reported
        if running is False:
            if previous is not False:
                self.reject("waiting_baseline")
            if fresh:
                self.baseline.append((reported, watts))
                self.baseline = [(t, v) for t, v in self.baseline if reported - t <= 180]
                if not stable(self.baseline):
                    self.baseline = [(reported, watts)]
                    self.status = "unstable_load"
                else:
                    self.status = (
                        "waiting_start"
                        if len(self.baseline) >= 3
                        and self.baseline[-1][0] - self.baseline[0][0] >= 60
                        else "waiting_baseline"
                    )
            return
        if running is not True:
            self.reject("ineligible")
            return
        if previous is False:
            if (
                changed is None
                or not 0 <= now - changed <= 60
                or len(self.baseline) < 3
                or self.baseline[-1][0] - self.baseline[0][0] < 60
                or not 0 <= changed - self.baseline[-1][0] <= 90
                or not stable(self.baseline)
            ):
                self.reject("waiting_baseline")
                return
            self.started = changed
            self.before_watts = median(v for _, v in self.baseline)
            self.cycle_key = cycle_key
            self.baseline.clear()
            self.after.clear()
        if self.started is None or self.before_watts is None:
            return
        if cycle_key != self.cycle_key:
            self.reject("changed_device")
            return
        if now - self.started > settle + 300:
            self.reject("unconfirmed_start")
            return
        self.status = "stabilizing"
        if confirmed is None or not self.started <= confirmed <= now:
            return
        if not fresh or reported < confirmed + settle:
            return
        self.after.append((reported, watts))
        if not stable(self.after):
            self.reject("unstable_load")
            return
        if len(self.after) < 3 or self.after[-1][0] - self.after[0][0] < 60:
            return
        delta = max(v for _, v in self.after) - self.before_watts
        if not 100 <= delta <= 10000:
            self.reject("ambiguous_delta")
            return
        # Require three consistent independent cycles. Never lower an established
        # estimate on the strength of a new, smaller aggregate-load observation.
        established = self.learned(now)
        proposed = (self.samples + [delta])[-5:]
        if established is not None and delta < established:
            self.reject("lower_sample")
            return
        if established is not None and max(proposed) - min(proposed) > median(proposed) * 0.2:
            self.reject("inconsistent_cycle")
            return
        self.samples = proposed
        self.updated_at = now
        self.reject("ready" if self.learned(now) is not None else "collecting")
