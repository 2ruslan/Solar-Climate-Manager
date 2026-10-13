"""Run without Home Assistant: python -m unittest discover -s tests/unit -v."""

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "scm_model", Path(__file__).parents[2] / "custom_components/solar_climate_manager/model.py"
)
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)


class ThermostatTests(unittest.TestCase):
    def decide(self, temperature, **kwargs):
        return model.evaluate(
            temperature,
            **{
                "target": 23,
                "hysteresis": 1,
                "mode": "heat",
                "previous_demand": False,
                "fresh": True,
                **kwargs,
            },
        )

    def test_heating_cycle(self):
        demand = False
        for temperature, expected in [
            (21.9, True),
            (22, True),
            (23, True),
            (24, True),
            (24.1, False),
            (23, False),
            (22, False),
        ]:
            decision = self.decide(temperature, previous_demand=demand)
            self.assertEqual(decision.demand, expected)
            demand = decision.demand

    def test_cooling_cycle(self):
        demand = False
        for temperature, expected in [
            (24.1, True),
            (24, True),
            (23, True),
            (22, True),
            (21.9, False),
            (23, False),
        ]:
            decision = self.decide(temperature, mode="cool", previous_demand=demand)
            self.assertEqual(decision.demand, expected)
            demand = decision.demand

    def test_invalid_data_clears_demand(self):
        for temperature in [None, float("nan"), float("inf")]:
            self.assertEqual(self.decide(temperature, previous_demand=True).reason, "invalid_data")
        for options in [{"fresh": False}, {"climate_valid": False}]:
            decision = self.decide(21, previous_demand=True, **options)
            self.assertFalse(decision.demand)
            self.assertFalse(decision.data_valid)

    def test_disabled(self):
        self.assertFalse(self.decide(20, enabled=False, previous_demand=True).demand)

    def test_invalid_settings(self):
        for options in [
            {"mode": "auto"},
            {"hysteresis": 0},
            {"hysteresis": -1},
            {"target": float("nan")},
        ]:
            with self.assertRaises(ValueError):
                self.decide(20, **options)

    def test_units_and_invalid_values(self):
        self.assertAlmostEqual(model.temperature_celsius("73.4", "°F"), 23)
        self.assertEqual(model.temperature_celsius("23", "°C"), 23)
        for value, unit in [
            ("unknown", "°C"),
            ("unavailable", "°C"),
            ("nan", "°C"),
            ("inf", "°C"),
            ("101", "°C"),
            ("23", None),
            ("23", "K"),
        ]:
            self.assertIsNone(model.temperature_celsius(value, unit))

    def test_freshness_boundaries(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(model.is_fresh(now, now - timedelta(seconds=900), 900))
        self.assertFalse(model.is_fresh(now, now - timedelta(seconds=901), 900))
        self.assertFalse(model.is_fresh(now, now + timedelta(seconds=1), 900))

    def test_independent_decisions(self):
        self.assertTrue(self.decide(23, previous_demand=True).demand)
        self.assertFalse(self.decide(23, previous_demand=False).demand)
