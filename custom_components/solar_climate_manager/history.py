"""Bounded diagnostic observations, independent of open browser sessions."""

from collections import deque
from copy import deepcopy

MAX_ROWS = 3000
MAX_AGE = 24 * 60 * 60
SAMPLE_INTERVAL = 60
MAX_SAMPLES = MAX_AGE // SAMPLE_INTERVAL + 1
MAX_EVENTS = MAX_ROWS - MAX_SAMPLES - 1
EVENT_KEYS = (
    "group_id",
    "running", "automation_mode", "control_allowed", "manual_pause", "demand",
    "strategy_action", "strategy_reason", "group_action", "group_reason",
    "group_command_status", "command_error", "command_failed", "grid_available",
    "invalid_data", "energy_data_invalid", "target_temperature", "power_accounting",
)


class DiagnosticHistory:
    def __init__(self):
        self.samples = deque(maxlen=MAX_SAMPLES)
        self.events = deque(maxlen=MAX_EVENTS)
        self.latest = None
        self.events_dropped_through = None

    def record(self, now, data, settings, event=None):
        # Public scalar telemetry only; no entity IDs or mutable runtime objects.
        state = {key: value for key, value in data.items()
                 if key != "group_name" and isinstance(value, (str, int, float, bool, type(None)))}
        state["target_temperature"] = settings.get("target_temperature")
        state["power_accounting"] = settings.get("power_accounting", "measured")
        self.prune(now)
        row = {"timestamp": now, "state": state}
        previous = self.latest["state"] if self.latest else None
        if event or previous is not None and any(previous.get(k) != state.get(k) for k in EVENT_KEYS):
            if len(self.events) == MAX_EVENTS:
                self.events_dropped_through = self.events[0]["timestamp"]
            self.events.append({**row, "kind": "event", "event": deepcopy(event) if event else {"type": "state_change"}})
        if not self.samples or now - self.samples[-1]["timestamp"] >= SAMPLE_INTERVAL:
            self.samples.append({**row, "kind": "sample"})
        self.latest = row

    def prune(self, now):
        for rows in (self.samples, self.events):
            while rows and rows[0]["timestamp"] < now - MAX_AGE:
                rows.popleft()
        if self.latest and self.latest["timestamp"] < now - MAX_AGE:
            self.latest = None

    def read(self, now):
        self.prune(now)
        rows = [*self.samples, *self.events]
        if self.latest and not any(row["timestamp"] == self.latest["timestamp"] and row["state"] == self.latest["state"] for row in rows):
            rows.append({**self.latest, "kind": "sample"})
        return deepcopy(sorted(rows, key=lambda row: row["timestamp"]))
