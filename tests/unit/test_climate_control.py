"""Temperature capability validation and acknowledgement boundaries."""

import importlib
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("scm_climate_control_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
sys.modules[package.__name__] = package
control = importlib.import_module("scm_climate_control_test.climate_control")


class ClimateControlTests(unittest.TestCase):
    def test_device_step_and_temperature_bounds(self):
        attrs = {"min_temp": 16, "max_temp": 30, "target_temp_step": 1}
        self.assertEqual(control.normalized_target(23.5, attrs, "°C"), 24)
        self.assertEqual(control.normalized_target(23.4, attrs, "°C"), 23)
        for target in (15, 31):
            with self.assertRaisesRegex(ValueError, "invalid_target"):
                control.normalized_target(target, attrs, "°C")

    def test_fahrenheit_and_missing_step(self):
        attrs = {"min_temp": 60, "max_temp": 86, "target_temp_step": 1}
        self.assertEqual(control.normalized_target(23, attrs, "°F"), 73)
        self.assertEqual(control.normalized_target(23, {}, "°F"), 73.4)
        self.assertTrue(control.temperature_matches(73.400001, 73.4))
        self.assertFalse(control.temperature_matches(74, 73.4))

    def test_unsupported_temperature_and_bad_optional_step(self):
        with self.assertRaisesRegex(ValueError, "unsupported_temperature"):
            control.normalized_target(23, {"supported_features": 0}, "°C")
        for step in (None, "unknown", 0, -1):
            self.assertEqual(control.normalized_target(23, {"target_temp_step": step}, "°C"), 23)
        self.assertEqual(control.normalized_target(23, {"supported_features": 1}, "°C"), 23)

    def test_acknowledgement_matches_only_commanded_changes(self):
        expected = {"hvac_mode": "heat", "temperature": 24}
        self.assertTrue(control.matches_acknowledgement({"temperature": 24.00001}, expected))
        self.assertFalse(control.matches_acknowledgement({"temperature": 25}, expected))
        self.assertFalse(
            control.matches_acknowledgement({"hvac_mode": "heat", "fan_mode": "quiet"}, expected)
        )
        self.assertFalse(control.matches_acknowledgement({}, expected))

    def test_invalid_target_numbers_are_rejected(self):
        for value in (None, True, float("nan"), float("inf"), "unknown"):
            with self.assertRaisesRegex(ValueError, "invalid_target"):
                control.normalized_target(value, {}, "°C")

    def test_compensation_matches_room_error_for_both_modes(self):
        self.assertEqual(control.compensated_target(22, 20, 25), 27)
        self.assertEqual(control.compensated_target(22, 26, 29), 25)
        self.assertEqual(control.compensated_target(22, 20, 18), 20)
        for missing in (None, float("nan"), "unknown"):
            self.assertIsNone(control.compensated_target(22, 20, missing))

    def test_compensation_limits_and_fahrenheit_rounding(self):
        attrs = {"min_temp": 16, "max_temp": 30, "target_temp_step": 1}
        self.assertEqual(control.normalized_target(40, attrs, "°C", clamp=True), 30)
        self.assertEqual(control.normalized_target(5, attrs, "°C", clamp=True), 16)
        attrs = {"min_temp": 60, "max_temp": 86, "target_temp_step": 1}
        self.assertEqual(control.normalized_target(27, attrs, "°F", clamp=True), 81)
