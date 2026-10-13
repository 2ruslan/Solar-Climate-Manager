"""Forecast coverage and timezone tests, including midnight boundaries."""

import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

package = types.ModuleType("scm_forecast_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
sys.modules[package.__name__] = package
forecast = importlib.import_module("scm_forecast_test.forecast")


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 13, 23, 45, tzinfo=timezone.utc)
        self.start = self.now - timedelta(minutes=15)
        self.records = [
            {
                "period_start": (self.start + timedelta(minutes=30 * i)).isoformat(),
                "pv_estimate": value,
            }
            for i, value in enumerate([2.8, 2.1, 1.8])
        ]

    def test_complete_midnight_forecast_converts_kw(self):
        self.assertEqual(forecast.covered_forecast(self.records, now=self.now), (2800, 2100, 1800))

    def test_missing_next_day_is_not_zero(self):
        self.assertIsNone(forecast.covered_forecast(self.records[:1], now=self.now))

    def test_gap_overlap_and_negative_invalid(self):
        self.assertIsNone(
            forecast.covered_forecast([self.records[0], self.records[2]], now=self.now)
        )
        self.assertIsNone(forecast.covered_forecast([*self.records, self.records[1]], now=self.now))
        self.records[1]["pv_estimate"] = -1
        self.assertIsNone(forecast.covered_forecast(self.records, now=self.now))

    def test_naive_dates_and_wrong_units_rejected(self):
        self.assertIsNone(forecast.aware_datetime("2026-10-13T20:00:00"))
        self.assertIsNone(forecast.covered_forecast(self.records, now=self.now, unit="kWh"))

    def test_half_hour_horizon(self):
        self.assertEqual(
            forecast.covered_forecast(self.records[:2], now=self.now, horizon_minutes=30),
            (2800, 2100),
        )
