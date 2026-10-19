"""Bounded diagnostic observations, independent of open browser sessions."""

from collections import deque
from copy import deepcopy

MAX_ROWS = 3000
MAX_AGE = 24 * 60 * 60


class DiagnosticHistory:
    def __init__(self):
        self.rows = deque(maxlen=MAX_ROWS)

    def record(self, now, data, settings):
        # Public scalar telemetry only; no entity IDs or mutable runtime objects.
        state = {key: value for key, value in data.items()
                 if key != "group_name" and isinstance(value, (str, int, float, bool, type(None)))}
        state["target_temperature"] = settings.get("target_temperature")
        state["power_accounting"] = settings.get("power_accounting", "measured")
        self.prune(now)
        if self.rows and self.rows[-1]["state"] == state and now - self.rows[-1]["timestamp"] < 60:
            return
        self.rows.append({"timestamp": now, "state": state})

    def prune(self, now):
        while self.rows and self.rows[0]["timestamp"] < now - MAX_AGE:
            self.rows.popleft()

    def read(self, now):
        self.prune(now)
        return deepcopy(list(self.rows))
