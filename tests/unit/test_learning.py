"""Learning accepts repeated isolated starts, never arbitrary load differences."""

import importlib
import unittest
from dataclasses import replace
from types import SimpleNamespace

import test_groups  # noqa: F401 -- installs the lightweight package boundary

module = importlib.import_module("scm_adapter_test.domain.learning")
MAX_AGE, PowerLearning = module.MAX_AGE, module.PowerLearning
adapter = importlib.import_module("scm_adapter_test.adapters.learning")
groups = test_groups.groups


def point(learning, time, watts, running=False, **changes):
    values = dict(
        now=time,
        reported=time,
        watts=watts,
        running=running,
        changed=70,
        confirmed=70,
        eligible=True,
        settle=30,
        cycle_key="heat:25",
    )
    values.update(changes)
    learning.observe(**values)


def cycle(learning, offset=0, delta=1200):
    for time in (0, 30, 60):
        point(learning, offset + time, 500)
    for time in (70, 100, 130, 160):
        point(
            learning, offset + time, 500 + delta, True, changed=offset + 70, confirmed=offset + 70
        )


class LearningTests(unittest.TestCase):
    def test_effective_policy_keeps_modes_and_applies_margin_once(self):
        group = groups.GroupConfig("g", "House")
        members = (groups.Membership("a", "g"),)
        settings = {
            "power_learning_enabled": True,
            "power_accounting": "estimated",
            "estimated_ac_power": 900,
        }
        coordinator = SimpleNamespace(settings=settings, power_learning=PowerLearning())
        learner = adapter.bind_learning(coordinator, group, members)
        learner.samples, learner.updated_at = [1200] * 3, 100
        policy = groups.MemberPolicy(power_accounting="estimated")
        self.assertEqual(
            adapter.effective_policy(coordinator, group, members, policy, 101).planned_watts, 1440
        )
        self.assertEqual(
            adapter.effective_policy(
                coordinator, group, members, replace(policy, power_accounting="legacy"), 101
            ).planned_watts,
            900,
        )
        settings["power_learning_enabled"] = False
        self.assertEqual(
            adapter.effective_policy(coordinator, group, members, policy, 101).planned_watts, 1080
        )
        settings["power_learning_enabled"] = True
        changed = replace(group, sources=groups.GroupSources(load_power_entity="sensor.new"))
        self.assertEqual(
            adapter.effective_policy(coordinator, changed, members, policy, 101).planned_watts, 1080
        )
        self.assertEqual(learner.samples, [1200] * 3)  # capturing state is read-only

    def test_three_cycles_required_and_margin_is_not_learned(self):
        learner = PowerLearning()
        for index in range(3):
            cycle(learner, index * 300)
            self.assertEqual(len(learner.samples), index + 1)
            self.assertEqual(learner.effective(900, index * 300 + 160), 1200 if index == 2 else 900)
        self.assertEqual(learner.effective(1400, 760), 1400)

    def test_repeated_reports_and_running_cycle_do_not_multiply_samples(self):
        learner = PowerLearning()
        cycle(learner)
        for time in range(161, 240):
            point(learner, time, 1700, True)
        self.assertEqual(learner.samples, [1200])

    def test_no_baseline_after_restart_or_manual_start(self):
        for confirmed in (None, 10):
            learner = PowerLearning()
            for time in (0, 30, 60, 100, 130, 160):
                point(learner, time, 1700, True, confirmed=confirmed)
            self.assertFalse(learner.samples)

    def test_unconfirmed_start_does_not_learn(self):
        learner = PowerLearning()
        for time in (0, 30, 60):
            point(learner, time, 500)
        for time in (70, 100, 130, 160, 400):
            point(learner, time, 1700, True, confirmed=None)
        self.assertFalse(learner.samples)

    def test_unstable_post_load_rejects_entire_cycle(self):
        learner = PowerLearning()
        for time in (0, 30, 60):
            point(learner, time, 500)
        for time, watts in ((70, 1700), (100, 1700), (130, 1900), (160, 1900), (190, 1900)):
            point(learner, time, watts, True)
        self.assertEqual(learner.status, "unstable_load")
        self.assertFalse(learner.samples)

    def test_stale_duplicate_and_future_reports_cannot_complete_window(self):
        for reported in (60, 1000, -1):
            learner = PowerLearning()
            for time in (0, 30, 60):
                point(learner, time, 500)
            for time in (70, 100, 130, 160):
                point(learner, time, 1700, True, reported=reported)
            self.assertFalse(learner.samples)

    def test_other_member_or_setting_change_invalidates_observation(self):
        for change in ({"eligible": False}, {"cycle_key": "heat:27"}):
            learner = PowerLearning()
            for time in (0, 30, 60):
                point(learner, time, 500)
            point(learner, 70, 1700, True)
            point(learner, 100, 1700, True, **change)
            for time in (130, 160, 190):
                point(learner, time, 1700, True)
            self.assertFalse(learner.samples)

    def test_ambiguous_or_inconsistent_deltas_do_not_activate(self):
        for delta in (-100, 0, 90, 11000):
            learner = PowerLearning()
            cycle(learner, delta=delta)
            self.assertFalse(learner.samples)
        learner = PowerLearning()
        for index, delta in enumerate((1000, 1500, 2000)):
            cycle(learner, index * 300, delta)
        self.assertIsNone(learner.learned(760))

    def test_smaller_observation_does_not_lower_established_estimate(self):
        learner = PowerLearning()
        for index in range(3):
            cycle(learner, index * 300)
        cycle(learner, 900, 1000)
        self.assertEqual(learner.learned(1060), 1200)
        self.assertEqual(learner.status, "lower_sample")

    def test_outlier_does_not_remove_previously_established_estimate(self):
        learner = PowerLearning()
        for index in range(3):
            cycle(learner, index * 300)
        cycle(learner, 900, 2000)
        self.assertEqual(learner.learned(1060), 1200)
        self.assertEqual(learner.status, "inconsistent_cycle")

    def test_new_sample_does_not_reactivate_expired_history(self):
        learner = PowerLearning(samples=[1200] * 3, updated_at=10)
        cycle(learner, MAX_AGE + 300)
        self.assertEqual(learner.samples, [1200])
        self.assertIsNone(learner.learned(MAX_AGE + 460))

    def test_restore_preserves_evidence_but_not_partial_cycle(self):
        learner = PowerLearning(context="installation")
        for index in range(3):
            cycle(learner, index * 300)
        restored = PowerLearning()
        restored.restore(learner.stored(), 800)
        self.assertEqual(restored.learned(800), 1200)
        self.assertIsNone(restored.was_running)
        self.assertFalse(restored.baseline)
        restored.bind("installation")
        self.assertEqual(restored.learned(800), 1200)
        restored.bind("changed installation or reset token")
        self.assertFalse(restored.samples)

    def test_invalid_expired_or_future_storage_falls_back(self):
        for sample in (True, float("nan"), -1, 10001, "1200"):
            learner = PowerLearning()
            learner.restore(
                {"version": 1, "context": "x", "samples": [sample] * 3, "updated_at": 10}, 20
            )
            self.assertFalse(learner.samples)
        learner = PowerLearning(samples=[1200] * 3, updated_at=10)
        self.assertEqual(learner.effective(900, MAX_AGE + 11), 900)
        self.assertEqual(learner.effective(900, 9), 900)


if __name__ == "__main__":
    unittest.main()
