"""Section merges must preserve hidden limits, other sources and disabled mode."""

import importlib
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("scm_settings_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
sys.modules[package.__name__] = package
settings = importlib.import_module("scm_settings_test.settings")


class SettingsTests(unittest.TestCase):
    def test_comfort_edit_keeps_energy_and_enabled(self):
        result = settings.merge_section(
            {
                "target_temperature": 23,
                "minimum_soc": 85,
                "enabled": False,
                "pv_power_entity": "sensor.pv",
            },
            {"target_temperature": 24},
        )
        self.assertEqual(result["minimum_soc"], 85)
        self.assertFalse(result["enabled"])
        self.assertEqual(result["pv_power_entity"], "sensor.pv")

    def test_source_clear_does_not_clear_other_section(self):
        result = settings.merge_section(
            {
                "pv_power_entity": "sensor.pv",
                "schedule_entity": "schedule.day",
                "minimum_run_time": 900,
            },
            {},
            clear_sources={"pv_power_entity"},
        )
        self.assertIsNone(result["pv_power_entity"])
        self.assertEqual(result["schedule_entity"], "schedule.day")
        self.assertEqual(result["minimum_run_time"], 900)

    def test_hidden_conditional_limits_retained(self):
        result = settings.merge_section(
            {"allow_grid_import": True, "max_grid_import": 700, "charging_reserve_power": 800},
            {"allow_grid_import": False},
        )
        self.assertEqual(result["max_grid_import"], 700)
        self.assertEqual(result["charging_reserve_power"], 800)

    def test_retired_rules_removed_and_advanced_group_separate(self):
        result = settings.merge_section(
            {"require_forecast": False, "enabled": False}, {}, removed=settings.RETIRED_RULES
        )
        self.assertNotIn("require_forecast", result)
        self.assertFalse(result["enabled"])
        self.assertFalse(settings.ADVANCED_KEYS & settings.ENERGY_KEYS)
