"""Exercise the actual bundled ruptures algorithm on synthetic meter traces."""
import importlib
import unittest

from test_groups import groups  # noqa: F401

t = importlib.import_module("scm_adapter_test.adapters.power_transitions")
c = {"mode": "heat", "fan": "high", "indoor": 20, "target": 24, "outdoor": 7, "phase": "steady"}


class TransitionTests(unittest.TestCase):
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
