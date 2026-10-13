"""Temporal budget is weighted by elapsed seconds, not by number of updates."""

import importlib
import sys
import types
import unittest
from pathlib import Path

package = types.ModuleType("scm_window_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
sys.modules[package.__name__] = package
BudgetWindow = importlib.import_module("scm_window_test.window").BudgetWindow


class WindowTests(unittest.TestCase):
    def test_short_peak_has_only_its_duration_weight(self):
        window = BudgetWindow()
        window.observe(0, 1000, 1000, 600)
        window.observe(590, -1000, 3000, 600)
        window.observe(600, 1000, 1000, 600)
        margin, required, observed = window.average(600, 600)
        self.assertAlmostEqual(margin, (590 * 1000 - 10 * 1000) / 600)
        self.assertEqual(observed, 600)

    def test_rapid_updates_do_not_inflate_peak_weight(self):
        window = BudgetWindow()
        window.observe(0, 1000, 1000, 600)
        for instant in range(590, 600):
            window.observe(instant, -1000, 3000, 600)
        window.observe(600, 1000, 1000, 600)
        self.assertAlmostEqual(window.average(600, 600)[0], 966.6666666667)

    def test_clock_reversal_and_clear_require_new_history(self):
        window = BudgetWindow()
        window.observe(600, 1000, 1000, 600)
        window.observe(500, 1000, 1000, 600)
        self.assertEqual(window.average(500, 600)[2], 0)
        window.clear()
        self.assertEqual(window.average(500, 600)[2], 0)

    def test_window_rolls_without_losing_boundary_sample(self):
        window = BudgetWindow()
        for instant, margin in [(0, -1000), (300, 1000), (900, 1000)]:
            window.observe(instant, margin, 1000, 600)
        self.assertEqual(window.average(900, 600)[0], 1000)
