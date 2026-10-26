"""Retention and immutable exports of diagnostic observations."""

import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "scm_history", Path(__file__).parents[2] / "custom_components/solar_climate_manager/history.py"
)
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


class HistoryTests(unittest.TestCase):
    def test_changes_and_periodic_samples(self):
        log = history.DiagnosticHistory()
        log.record(100, {"running": False}, {})
        log.record(130, {"running": False}, {})
        log.record(160, {"running": False}, {})
        log.record(161, {"running": True}, {})
        log.record(161, {"running": True, "command_failed": True}, {})
        self.assertEqual(len(log.read(161)), 4)

    def test_bounded_and_expired(self):
        log = history.DiagnosticHistory()
        for timestamp in range(history.MAX_ROWS + 20):
            log.record(timestamp, {"temperature": timestamp, "running": bool(timestamp % 2)}, {})
        self.assertLessEqual(len(log.read(history.MAX_ROWS + 20)), history.MAX_ROWS)
        self.assertIsNotNone(log.events_dropped_through)
        self.assertEqual(log.read(history.MAX_AGE + history.MAX_ROWS + 20), [])

    def test_fast_telemetry_cannot_evict_twelve_hours_of_samples(self):
        log = history.DiagnosticHistory()
        for timestamp in range(12 * 3600 + 1):
            log.record(timestamp, {"temperature": timestamp % 30, "running": True}, {})
        rows = log.read(12 * 3600)
        self.assertEqual(rows[0]["timestamp"], 0)
        self.assertEqual(rows[-1]["timestamp"], 12 * 3600)
        self.assertEqual(len(rows), 721)
        self.assertFalse(log.events)

    def test_external_change_is_copied_and_keeps_exact_time(self):
        log = history.DiagnosticHistory()
        log.record(0, {"running": True}, {})
        event = {"type": "external_change", "changes": {"state": {"before": "heat", "after": "off"}}}
        log.record(1, {"running": False}, {}, event=event)
        event["changes"].clear()
        rows = log.read(1)
        self.assertEqual(rows[-1]["timestamp"], 1)
        self.assertEqual(rows[-1]["event"]["changes"]["state"]["after"], "off")

    def test_export_copy_and_target_change(self):
        log = history.DiagnosticHistory()
        log.record(100, {"temperature": None, "group_name": "private"}, {"target_temperature": 20})
        log.record(101, {"temperature": None, "group_name": "private"}, {"target_temperature": 21})
        rows = log.read(101)
        self.assertEqual(len(rows), 2)
        self.assertNotIn("group_name", rows[0]["state"])
        rows[0]["state"]["temperature"] = 0
        self.assertIsNone(log.read(101)[0]["state"]["temperature"])
