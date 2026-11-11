"""Confidence is based on independent, quality-weighted cycles."""
import importlib
import unittest

from test_groups import groups  # noqa: F401

p = importlib.import_module("scm_adapter_test.domain.transition_profiles")


def samples(cycle, count=20, value=700, quality=1., reasons=None):
    return [{"cycle": cycle, "time": cycle+i*60, "estimate": value, "quality": quality,
             "low": max(0, value-150), "high": value+150, "seconds": 60,
             "reasons": reasons or ["transition_estimate"]} for i in range(count)]


class TransitionProfileTests(unittest.TestCase):
    def test_one_long_cycle_does_not_outvote_repeated_short_cycles(self):
        rows = samples(0, 1000, 1800)+samples(100000)+samples(200000)+samples(300000)
        view = p.summarize(rows, 302000)
        self.assertEqual(view["estimate"], 700)
        self.assertEqual(view["supported_cycles"], 3)
        self.assertEqual(view["confidence"], "moderate")

    def test_one_bad_sample_does_not_poison_profile(self):
        rows = sum((samples(i*10000) for i in range(4)), [])
        rows[0].update(quality=.1, reasons=["noisy_background"], estimate=4000)
        view = p.summarize(rows, 32000)
        self.assertEqual(view["confidence"], "moderate")
        self.assertEqual(view["estimate"], 700)
        self.assertNotIn("noisy_background", view["reasons"])

    def test_repeated_single_edges_can_support_moderate_confidence(self):
        rows = sum((samples(i*10000, quality=.75, reasons=["single_transition"]) for i in range(4)), [])
        self.assertEqual(p.summarize(rows, 32000)["confidence"], "moderate")

    def test_many_minutes_do_not_replace_independent_cycles(self):
        self.assertEqual(p.summarize(samples(0, 500), 30000)["confidence"], "low")

    def test_inconsistent_cycles_and_weak_baseline_remain_low(self):
        rows = sum((samples(i*10000, value=value) for i, value in enumerate((200, 700, 1800, 3000))), [])
        self.assertEqual(p.summarize(rows, 32000)["confidence"], "low")
        rows = sum((samples(i*10000, quality=.2) for i in range(4)), [])
        self.assertEqual(p.summarize(rows, 32000)["confidence"], "low")
