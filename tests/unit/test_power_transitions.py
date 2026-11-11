"""Exercise the actual bundled ruptures algorithm on synthetic meter traces."""
import importlib
import unittest

from test_groups import groups  # noqa: F401

t = importlib.import_module("scm_adapter_test.adapters.power_transitions")
c = {"mode": "heat", "fan": "high", "indoor": 20, "target": 24, "outdoor": 7, "phase": "steady"}


class TransitionTests(unittest.TestCase):
    def test_short_cycle_clips_windows_at_neighbouring_transitions(self):
        trace = [(i*60, 1300 if 4 <= i < 9 else 600,
                  {"ac": c if 4 <= i < 9 else None}) for i in range(14)]
        rows, count = t.detect(trace)
        self.assertEqual(count, 2)
        self.assertEqual(len(rows["ac"]), 5)
        self.assertEqual({r["estimate"] for r in rows["ac"]}, {700})

    def test_long_paired_cycle_keeps_middle_and_separates_startup(self):
        trace = [(i*60, 1300 if 10 <= i < 250 else 600,
                  {"ac": c if 10 <= i < 250 else None}) for i in range(260)]
        rows, count = t.detect(trace)
        self.assertEqual(count, 2)
        self.assertEqual(len(rows["ac"]), 240)
        self.assertEqual(rows["ac"][5]["conditions"]["phase"], "startup")
        self.assertEqual(rows["ac"][120]["conditions"]["phase"], "steady")
        self.assertIn("distant_background", rows["ac"][120]["reasons"])
        self.assertEqual(rows["ac"][120]["estimate"], 700)

    def test_long_single_edge_is_retained_with_reduced_quality(self):
        trace = [(i*60, 1300 if i >= 10 else 600, {"ac": c if i >= 10 else None}) for i in range(500)]
        rows, count = t.detect(trace)
        self.assertEqual(count, 1)
        self.assertEqual(rows["ac"][-1]["time"], 370*60)
        self.assertLess(rows["ac"][-1]["quality"], rows["ac"][20]["quality"])

    def test_setpoint_change_does_not_smear_previous_power(self):
        trace = [(i*60, 600 if i < 10 else 1300 if i < 30 else 2300,
                  {"ac": None if i < 10 else {**c, "target": 24 if i < 30 else 27}}) for i in range(50)]
        rows, _ = t.detect(trace)
        changed = next(r for r in rows["ac"] if r["time"] == 30*60)
        self.assertEqual(changed["conditions"]["phase"], "settling")
        self.assertEqual(changed["estimate"], 1700)

    def test_near_background_zero_is_explicitly_uncertain(self):
        trace = self.trace()
        trace[25:35] = [(i*60, 100, {"ac": c}) for i in range(25, 35)]
        rows, _ = t.detect(trace)
        zero = next(r for r in rows["ac"] if r["time"] == 30*60)
        self.assertEqual(zero["estimate"], 0)
        self.assertIn("near_background", zero["reasons"])
        self.assertLess(zero["quality"], .5)

    def trace(self, spike=False):
        return [(i*60, (1300 if 10 <= i < 40 else 600)+(3000 if spike and i == 22 else 0),
                 {"ac": c if 10 <= i < 40 else None}) for i in range(50)]

    def test_local_baseline_and_both_edges_ignore_short_spike(self):
        rows, count = t.detect(self.trace(True))
        self.assertEqual(count, 2)
        self.assertEqual(len(rows["ac"]), 30)
        self.assertEqual({r["estimate"] for r in rows["ac"]}, {700})
        self.assertTrue(all(r["source"] == "ruptures" for r in rows["ac"]))

    def test_single_start_can_estimate_before_switch_off(self):
        rows, count = t.detect(self.trace()[:30])
        self.assertEqual(count, 1)
        self.assertEqual(rows["ac"][-1]["estimate"], 700)
        self.assertIn("single_transition", rows["ac"][-1]["reasons"])

    def test_no_step_or_gap_or_overlap_does_not_invent_an_anchor(self):
        trace = self.trace()
        flat = [(stamp, 600, members) for stamp, _, members in trace]
        overlap = [(stamp, watts, {**members, "other": c}) for stamp, watts, members in trace]
        gap = [(stamp+(600 if i >= 10 else 0)+(600 if i >= 40 else 0), watts, members)
               for i, (stamp, watts, members) in enumerate(trace)]
        for records in (flat, overlap, gap):
            self.assertEqual(t.detect(records), ({}, 0))

    def test_unrelated_step_far_from_ac_start_is_rejected(self):
        trace = [(i*60, 600 if i < 16 else 1800, {"ac": c if i >= 10 else None}) for i in range(30)]
        self.assertEqual(t.detect(trace), ({}, 0))
