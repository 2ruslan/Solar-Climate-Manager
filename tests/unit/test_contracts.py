"""An intent must never masquerade as a physical device report."""

import importlib
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace

from test_strategy import policy

models = importlib.import_module("scm_strategy_test.domain.types")
settings = importlib.import_module("scm_strategy_test.settings")


class PolicyContractTests(unittest.TestCase):
    def setUp(self):
        self.cfg = policy.EnergyPolicyConfig()
        self.snapshot = policy.EnergySnapshot(grid=True, soc=95, battery=0)
        self.observed = policy.ObservedDeviceState()
        self.state = policy.PolicyState()

    def decide(self, now=1000, **changes):
        return policy.decide(
            replace(self.snapshot, **changes), self.observed, self.state, self.cfg,
            now=now, demand=True,
        )

    def test_unconfirmed_start_does_not_start_physical_cycle(self):
        first = self.decide()
        self.assertEqual(first.decision.action, "start")
        self.assertTrue(first.decision.intent.running)
        self.state = first.policy
        self.assertEqual(self.decide(1030).decision.action, "start")
        self.assertEqual(self.observed, policy.ObservedDeviceState())
        saved = policy.serialize(self.observed, self.state)
        self.assertFalse(saved["running"])
        self.assertIsNone(saved["last_start"])
        self.observed = self.observed.observe(True, 1040)
        result = policy.decide(
            self.snapshot, self.observed, self.state, self.cfg, now=1100, demand=False,
        )
        self.assertEqual(result.decision.reason, "minimum_run")
        self.assertEqual(result.decision.seconds_to_stop, 540)

    def test_protective_stop_preserves_running_until_device_report(self):
        self.observed = policy.ObservedDeviceState(running=True, last_start=900)
        result = self.decide(grid=False, soc=40)
        self.assertEqual(result.decision.action, "stop")
        self.assertFalse(result.decision.intent.running)
        self.assertTrue(self.observed.running)
        self.assertIsNone(self.observed.last_stop)
        self.assertFalse(self.state.soc_blocked)
        self.assertTrue(result.policy.soc_blocked)
        self.state = result.policy
        self.assertEqual(self.decide(1030, grid=False, soc=40).decision.action, "stop")
        self.observed = self.observed.observe(False, 1040)
        self.assertEqual(self.observed.last_stop, 1040)
        self.assertEqual(self.decide(1100).decision.seconds_to_start, 540)

    def test_evaluations_do_not_share_or_mutate_window_history(self):
        self.state.window.observe(0, 200, 1000, 600)
        before = deepcopy(self.state.window.samples)
        result = self.decide(pv=2000, load=500)
        self.assertEqual(self.state.window.samples, before)
        self.assertIsNot(result.policy.window, self.state.window)
        result.policy.window.clear()
        self.assertEqual(self.state.window.samples, before)
        self.decide(soc=None)
        self.assertEqual(self.state.window.samples, before)

    def test_unchanged_report_preserves_deadline_and_observation_is_immutable(self):
        running = self.observed.observe(True, 1000)
        self.assertIs(running.observe(True, 1500), running)
        with self.assertRaises(FrozenInstanceError):
            running.running = False

    def test_store_v1_restore_preserves_cycle_and_resets_continuity(self):
        legacy = {
            "running": True, "last_start": 900, "last_stop": 100,
            "soc_blocked": True, "surplus_since": 850, "deficit_since": 950,
            "grid_absent_since": 800,
        }
        observed, state = policy.restore(legacy, 1000)
        self.assertEqual(observed, policy.ObservedDeviceState(True, 900, 100))
        self.assertTrue(state.soc_blocked)
        self.assertIsNone(state.deficit_since)
        self.assertIsNone(state.grid_absent_since)
        self.assertFalse(state.window.samples)
        self.assertEqual(set(policy.serialize(observed, state)), set(legacy))

    def test_normalized_legacy_options_feed_typed_configuration(self):
        defaults = {
            **policy.STRATEGY_DEFAULTS, "climate_entity": "climate.ac",
            "temperature_entity": "sensor.room", "target_temperature": 23,
            "power_max_data_age": 900,
        }
        values = settings.configuration_values(
            {"minimum_soc": 80, "enabled": False, "grid_absence_delay": 120},
            {"target_temperature": 24}, defaults, (),
        )
        device = models.DeviceConfig.from_settings(values)
        energy = models.EnergyPolicyConfig.from_settings(values)
        self.assertEqual(device.operation_mode, "disabled")
        self.assertEqual(device.target_temperature, 24)
        self.assertEqual(energy.restart_soc, 85)
        self.assertEqual(energy.grid_absence_delay, 120)
        self.assertEqual(device.climate_entity, "climate.ac")
        self.assertNotIn("climate_entity", energy.as_settings())

    def test_command_tracking_is_separate_for_each_device(self):
        first, second = models.CommandState(), models.CommandState()
        first.contexts["command"] = 1030
        first.expected_updates.append(models.ExpectedUpdate(1030, {"hvac_mode": "heat"}))
        first.unconfirmed_start = True
        self.assertFalse(second.contexts)
        self.assertFalse(second.expected_updates)
        self.assertFalse(second.unconfirmed_start)
        self.assertFalse(self.observed.running)
