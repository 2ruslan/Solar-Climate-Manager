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
    def test_fan_speed_uses_absolute_room_error_and_exact_boundary(self):
        attrs = {"fan_modes": ["Auto", "low", "High"]}
        for current, expected in ((20, "High"), (21.99, "High"), (22, "Auto"),
                                  (23, "Auto"), (24, "Auto"), (24.01, "High")):
            with self.subTest(current=current):
                self.assertEqual(control.desired_fan_mode(23, current, attrs), expected)
        for current in (None, float("nan"), float("inf")):
            self.assertIsNone(control.desired_fan_mode(23, current, attrs))

    def test_fan_speed_selects_supported_maximum_or_auto_fallback(self):
        for modes, expected in ((["auto", "high", "max"], "max"),
                                (["auto", "high", "turbo"], "turbo"),
                                (["auto", "1", "5", "3"], "5"),
                                (["auto", "low"], "auto"),
                                (["unknown"], None), (None, None)):
            with self.subTest(modes=modes):
                self.assertEqual(control.desired_fan_mode(23, 20, {"fan_modes": modes}), expected)

    def test_compensation_refresh_uses_remaining_device_reserve(self):
        for mode, target, ample, boundary, small, crossed in (
            ("heat", 26, 24, 24.9, 25, 27),
            ("cool", 22, 24, 23.1, 23, 21),
        ):
            self.assertFalse(control.compensation_needed(target, ample, mode))
            self.assertFalse(control.compensation_needed(target, boundary, mode))
            self.assertTrue(control.compensation_needed(target, small, mode))
            self.assertTrue(control.compensation_needed(target, crossed, mode))
        self.assertTrue(control.compensation_needed(None, 23, "heat"))

    def test_configured_bounds_intersect_device_range_and_step(self):
        limits = (15, 27)
        self.assertEqual(control.normalized_target(40, {}, "°C", clamp=True, bounds_c=limits), 27)
        self.assertEqual(control.normalized_target(5, {}, "°C", clamp=True, bounds_c=limits), 15)
        attrs = {"min_temp": 16, "max_temp": 30, "target_temp_step": 1}
        self.assertEqual(control.normalized_target(5, attrs, "°C", clamp=True, bounds_c=limits), 16)
        attrs = {"min_temp": 10, "max_temp": 35, "target_temp_step": 3}
        self.assertEqual(control.normalized_target(5, attrs, "°C", clamp=True, bounds_c=limits), 16)
        self.assertEqual(control.normalized_target(40, attrs, "°C", clamp=True, bounds_c=limits), 25)
        self.assertEqual(control.normalized_target(40, {}, "°F", clamp=True, bounds_c=limits), 80.6)
        self.assertEqual(control.normalized_target(5, {}, "°F", clamp=True, bounds_c=limits), 59)
        for bounds in ((28, 27), (float("nan"), 27), (None, 27)):
            with self.assertRaisesRegex(ValueError, "invalid_ac_temperature_limits"):
                control.normalized_target(23, {}, "°C", clamp=True, bounds_c=bounds)
        for attrs in ({"min_temp": 28}, {"max_temp": 14}, {
            "min_temp": 10, "target_temp_step": 3,
        }):
            with self.assertRaisesRegex(ValueError, "invalid_ac_temperature_limits"):
                control.normalized_target(23, attrs, "°C", clamp=True, bounds_c=(15, 15))
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
