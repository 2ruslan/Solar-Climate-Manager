"""Test power validation without installing Home Assistant."""

import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

package = types.ModuleType("scm_power_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
sys.modules[package.__name__] = package
power = importlib.import_module("scm_power_test.power")


class PowerTests(unittest.TestCase):
    def test_signed_power_and_soc(self):
        self.assertEqual(power.signed_power_watts("-1.5", "kW"), -1500)
        self.assertEqual(power.soc_percent("90", "%"), 90)
        for value, unit in [(101, "%"), (-1, "%"), ("nan", "%"), (90, None)]:
            self.assertIsNone(power.soc_percent(value, unit))

    def test_watts_and_kilowatts(self):
        self.assertEqual(power.power_watts("2800", "W"), 2800)
        self.assertEqual(power.power_watts("2.8", "kW"), 2800)
        self.assertEqual(power.power_watts("0", "W"), 0)

    def test_reject_energy_and_bad_measurements(self):
        for value, unit in [
            (1, "kWh"),
            (1, "Wh"),
            (1, None),
            (-1, "W"),
            ("nan", "W"),
            ("inf", "kW"),
            ("unavailable", "W"),
            (None, "W"),
            (True, "W"),
        ]:
            self.assertIsNone(power.power_watts(value, unit))

    def test_stale_and_future_never_become_zero(self):
        now = datetime.now(timezone.utc)
        for reported in [now - timedelta(seconds=901), now + timedelta(seconds=1)]:
            self.assertIsNone(
                power.read_power("2800", "W", now=now, reported=reported, max_age=900)
            )
        self.assertEqual(power.read_power("2.8", "kW", now=now, reported=now, max_age=900), 2800)

    def test_independent_source_freshness(self):
        now = datetime.now(timezone.utc)
        reported = now - timedelta(seconds=1000)
        self.assertIsNone(power.read_power(2800, "W", now=now, reported=reported, max_age=900))
        self.assertEqual(
            power.read_power(3000, "W", now=now, reported=reported, max_age=1800), 3000
        )
