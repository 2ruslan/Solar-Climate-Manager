"""Independent cycles, background confounding and bounded passive persistence."""

import importlib
import unittest
from dataclasses import replace

from test_groups import groups  # noqa: F401

p = importlib.import_module("scm_adapter_test.domain.power_analysis")


class PowerAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.model = p.GroupAnalysis(context="installation")
        self.conditions = p.Conditions("heat", "auto", 21, 24, 5)

    def point(self, time, watts, active=False, **kwargs):
        self.model.observe(now=time, reported=time, watts=watts,
                           members={"ac": self.conditions if active else None}, **kwargs)

    def cycle(self, base, power=600, after=300):
        for t in range(0, 121, 30):
            self.point(base + t, 300)
        for t in range(150, 961, 30):
            self.point(base + t, 300 + power, True)
        for t in range(990, 1111, 30):
            self.point(base + t, after)

    def test_background_collected_while_off_and_no_model_from_one_cycle(self):
        self.cycle(1000)
        self.assertGreaterEqual(len(self.model.background), 8)
        view = self.model.estimate("ac", self.conditions, 2110)
        self.assertEqual(view["cycles"], 1)
        self.assertEqual(view["confidence"], "insufficient")
        self.assertIsNone(view["watts"])
        self.assertTrue(view["analysis_only"])

    def test_profiles_need_independent_cycles_and_preserve_modes(self):
        for n, watts in enumerate((600, 620, 590, 610, 600)):
            self.cycle(1000 + n * 1500, watts)
        view = self.model.estimate("ac", self.conditions, 8110)
        self.assertEqual(view["watts"], 600)
        self.assertEqual(view["matching_cycles"], 5)
        self.assertEqual(view["confidence"], "moderate")
        for changed in (replace(self.conditions, fan="high"),
                        replace(self.conditions, mode="cool"),
                        replace(self.conditions, target=30),
                        replace(self.conditions, outdoor=-10)):
            self.assertIsNone(self.model.estimate("ac", changed, 8110)["watts"])
        startup = replace(self.conditions, phase="startup")
        self.assertEqual(self.model.estimate("ac", startup, 8110)["matching_cycles"], 5)

    def test_changed_background_rejects_whole_cycle(self):
        self.cycle(1000, after=1000)
        self.assertFalse(self.model.profiles)
        self.assertEqual(self.model.rejected_cycles, 1)

    def test_overlapping_devices_cannot_train_individual_profile(self):
        for t in (1000, 1030, 1060):
            self.point(t, 300)
        self.point(1090, 900, True)
        self.model.observe(now=1120, reported=1120, watts=1500,
                           members={"ac": self.conditions, "other": self.conditions})
        self.assertEqual(self.model.status, "multiple_running")
        self.assertIsNone(self.model.active)
        self.assertFalse(self.model.profiles)

    def test_stale_duplicate_and_missing_reports_do_not_create_evidence(self):
        self.point(1000, 300)
        for _ in range(50):
            self.point(1000, 300)
        self.assertEqual(len(self.model.background), 1)
        self.point(1030, 300)
        self.point(1060, 300)
        self.point(1090, 900, True)
        self.point(1300, 900, True)
        self.assertIsNone(self.model.active)
        self.point(1330, None, True)
        self.assertEqual(self.model.status, "invalid_data")

    def test_overlap_is_rejected_before_the_next_meter_report(self):
        for t in (1000, 1030, 1060):
            self.point(t, 300)
        self.point(1090, 900, True)
        self.model.observe(now=1091, reported=1090, watts=900,
                           members={"ac": self.conditions, "other": self.conditions})
        self.assertEqual(self.model.status, "multiple_running")
        self.assertIsNone(self.model.active)

    def test_restore_keeps_profiles_but_never_resumes_unfinished_cycle(self):
        for n in range(3):
            self.cycle(1000 + n * 1500)
        self.point(5140, 900, True)
        saved = self.model.stored()
        restored = p.GroupAnalysis.restore(saved, 5200)
        self.assertEqual(restored.estimate("ac", self.conditions, 5200)["watts"], 600)
        self.assertIsNone(restored.active)
        self.assertEqual(restored.baseline, [])
        restored.prune(5200 + p.RETENTION + 1)
        self.assertEqual(restored.background, [])
        self.assertIsNone(restored.estimate("ac", self.conditions, 5200 + p.RETENTION + 1)["watts"])

    def test_corrupt_storage_is_ignored_and_storage_does_not_alias_lists(self):
        self.cycle(1000)
        saved = self.model.stored()
        count = len(saved["background"])
        self.point(2140, 300)
        self.assertEqual(len(saved["background"]), count)
        saved["profiles"]["ac"].append({"time": float("nan")})
        saved["background"].append([float("inf"), 300])
        restored = p.GroupAnalysis.restore(saved, 2200)
        self.assertEqual(restored.estimate("ac", self.conditions, 2200)["cycles"], 1)
        self.assertEqual(p.GroupAnalysis.restore({"context": []}, 2200).context, "")

    def test_late_reports_cannot_finish_a_cycle_across_a_gap(self):
        for t in (1000, 1030, 1060):
            self.point(t, 300)
        self.point(1090, 900, True)
        self.model.observe(now=1300, reported=1090, watts=900,
                           members={"ac": self.conditions})
        self.assertEqual(self.model.status, "invalid_data")
        self.assertFalse(self.model.pending)

    def test_setting_change_waits_for_new_stable_window(self):
        for t in (1000, 1030, 1060):
            self.point(t, 300)
        for t in range(1090, 1301, 30):
            self.point(t, 900, True)
        count = len(self.model.pending)
        self.conditions = replace(self.conditions, fan="high", target=25)
        self.point(1330, 1200, True)
        self.assertEqual(self.model.status, "settling")
        self.assertEqual(len(self.model.pending), count)
