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
            log.record(timestamp, {"temperature": timestamp}, {})
        self.assertEqual(len(log.read(history.MAX_ROWS + 20)), history.MAX_ROWS)
        self.assertEqual(log.read(history.MAX_AGE + history.MAX_ROWS + 20), [])

    def test_export_copy_and_target_change(self):
        log = history.DiagnosticHistory()
        log.record(100, {"temperature": None, "group_name": "private"}, {"target_temperature": 20})
        log.record(101, {"temperature": None, "group_name": "private"}, {"target_temperature": 21})
        rows = log.read(101)
        self.assertEqual(len(rows), 2)
        self.assertNotIn("group_name", rows[0]["state"])
        rows[0]["state"]["temperature"] = 0
        self.assertIsNone(log.read(101)[0]["state"]["temperature"])
