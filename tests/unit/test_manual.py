"""Manual changes and local-date pause semantics."""

import ast
import importlib
import sys
import types
import unittest
from datetime import date
from pathlib import Path

root = Path(__file__).parents[2] / "custom_components/solar_climate_manager"
package = types.ModuleType("scm_manual_test")
package.__path__ = [str(root)]
sys.modules[package.__name__] = package
manual = importlib.import_module("scm_manual_test.manual")


class ManualTests(unittest.TestCase):
    def test_ambient_temperature_and_action_do_not_pause(self):
        first = manual.control_fingerprint(
            "heat", {"temperature": 23, "current_temperature": 20, "hvac_action": "heating"}
        )
        second = manual.control_fingerprint(
            "heat", {"temperature": 23, "current_temperature": 21, "hvac_action": "idle"}
        )
        self.assertEqual(first, second)

    def test_control_changes_detected(self):
        baseline = manual.control_fingerprint("heat", {"temperature": 23, "fan_mode": "auto"})
        for state, attributes in [
            ("off", {"temperature": 23, "fan_mode": "auto"}),
            ("heat", {"temperature": 24, "fan_mode": "auto"}),
            ("heat", {"temperature": 23, "fan_mode": "quiet"}),
        ]:
            self.assertNotEqual(baseline, manual.control_fingerprint(state, attributes))
        self.assertIsNone(manual.control_fingerprint("unavailable", {}))

    def test_pause_expires_on_next_local_date(self):
        self.assertTrue(manual.pause_active("2026-10-13", date(2026, 10, 13)))
        self.assertFalse(manual.pause_active("2026-10-13", date(2026, 10, 14)))
        self.assertFalse(manual.pause_active(None, date(2026, 10, 13)))

    def test_policy_modules_have_no_device_io(self):
        for path in (root / name for name in ("strategy.py", "model.py", "manual.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertNotIn(
                        node.func.attr,
                        {
                            "async_call",
                            "call_service",
                            "async_turn_on",
                            "async_turn_off",
                            "async_set_temperature",
                            "async_set_hvac_mode",
                        },
                        str(path),
                    )
