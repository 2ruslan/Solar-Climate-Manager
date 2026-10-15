"""Time-weighted balance; rapid sensor updates do not outweigh long observations."""


class BudgetWindow:
    def __init__(self) -> None:
        self.samples: list[tuple[float, float, float]] = []

    def clear(self) -> None:
        self.samples.clear()

    def observe(self, now: float, margin: float, required: float, duration: float) -> None:
        if self.samples and now < self.samples[-1][0]:
            self.clear()
        point = (now, margin, required)
        if self.samples and now == self.samples[-1][0]:
            self.samples[-1] = point
        else:
            self.samples.append(point)
        while len(self.samples) > 1 and self.samples[1][0] <= now - duration:
            self.samples.pop(0)

    def average(
        self,
        now: float,
        duration: float,
    ) -> tuple[float | None, float | None, float]:
        if not self.samples:
            return None, None, 0
        start = max(now - duration, self.samples[0][0])
        elapsed = max(0, now - start)
        if not elapsed:
            return self.samples[-1][1], self.samples[-1][2], 0
        margin_total = required_total = 0.0
        for index, (time, margin, required) in enumerate(self.samples):
            finish = self.samples[index + 1][0] if index + 1 < len(self.samples) else now
            weight = max(0, min(now, finish) - max(start, time))
            margin_total += margin * weight
            required_total += required * weight
        return margin_total / elapsed, required_total / elapsed, elapsed
