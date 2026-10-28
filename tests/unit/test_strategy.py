"""Comfort-first grid operation and conservative battery reserve protection."""

import importlib
import sys
import types
import unittest
from dataclasses import replace
from pathlib import Path

package = types.ModuleType("scm_strategy_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
sys.modules[package.__name__] = package
policy = importlib.import_module("scm_strategy_test.strategy")
storage = importlib.import_module("scm_strategy_test.adapters.storage")


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.observed = policy.ObservedDeviceState()
        self.state = policy.PolicyState()
        self.snapshot = policy.EnergySnapshot(
            pv=2800,
            load=600,
            soc=95,
            battery=0,
            grid_power=0,
            grid=False,
        )
        self.cfg = {
            **policy.STRATEGY_DEFAULTS,
            "start_delay": 60,
            "shortage_delay": 60,
            "minimum_run_time": 120,
            "minimum_off_time": 120,
            "grid_absence_delay": 60,
        }

    def decide(self, now=0, snapshot=None, demand=True, **kwargs):
        evaluation = policy.decide(
            snapshot or self.snapshot, self.observed, self.state,
            policy.EnergyPolicyConfig.from_settings(self.cfg), now=now, demand=demand, **kwargs
        )
        self.state = evaluation.policy
        # These policy scenarios model an ideal device that confirms each intent immediately.
        # Delayed/failed confirmation is exercised separately in contract and adapter tests.
        self.observed = self.observed.observe(evaluation.decision.intent.running, now)
        return evaluation.decision

    def start_solar(self):
        self.assertEqual(self.decide(0).action, "start")
        self.assertEqual(self.decide(60).action, "continue")

    def test_forecast_adds_only_positive_delta_to_solar_budget(self):
        for forecast, action in (
            (2000, "start"), (1000, "wait"), (500, "wait"),
            (None, "wait"), (float("nan"), "wait"), (float("inf"), "wait"),
        ):
            with self.subTest(forecast=forecast):
                self.setUp()
                snapshot = replace(self.snapshot, pv=1000, generation_forecast=forecast)
                self.assertEqual(self.decide(snapshot=snapshot).action, action)
        self.setUp()
        snapshot = replace(self.snapshot, pv=None, generation_forecast=5000)
        self.assertEqual(self.decide(snapshot=snapshot).reason, "invalid_energy_data")

    def test_outdoor_guard_stops_immediately_and_blocks_restart(self):
        for reason in ("low_outdoor_temperature", "outdoor_temperature_unavailable"):
            with self.subTest(reason=reason):
                self.observed = policy.ObservedDeviceState(running=True, last_start=99)
                blocked = replace(self.snapshot, grid=True, outdoor_block_reason=reason)
                decision = self.decide(100, snapshot=blocked)
                self.assertEqual((decision.action, decision.reason), ("stop", reason))
                self.assertEqual(self.decide(101, snapshot=blocked).action, "wait")
                recovered = replace(blocked, outdoor_block_reason=None)
                self.assertEqual(self.decide(102, snapshot=recovered).reason, "minimum_off")
                self.assertEqual(self.decide(221, snapshot=recovered).action, "start")

    def test_grid_heats_at_night_without_forecast_or_pv(self):
        grid = replace(
            self.snapshot,
            grid=True,
            pv=None,
            load=None,
            grid_power=None,
        )
        self.assertEqual(self.decide(0, grid).reason, "grid_ready")
        self.assertEqual(self.decide(1000, grid).action, "continue")

    def test_unlimited_grid_import_is_not_a_stop_condition(self):
        grid = replace(self.snapshot, grid=True, pv=0, load=6000, grid_power=6900)
        self.assertEqual(self.decide(0, grid).action, "start")
        self.assertEqual(self.decide(1000, grid).action, "continue")

    def test_solar_start_requires_only_current_budget(self):
        self.assertEqual(self.decide(0).action, "start")

    def test_low_soc_immediate_off_grid(self):
        self.observed = policy.ObservedDeviceState(running=True, last_start=0)
        self.state = policy.PolicyState()
        result = self.decide(1, replace(self.snapshot, grid=False, soc=84, pv=0))
        self.assertEqual(result.reason, "low_soc")
        self.assertFalse(self.observed.running)

    def test_solar_forecast_starts_and_continues_below_both_soc_thresholds(self):
        for soc in (0, 20, 84, 89):
            with self.subTest(soc=soc):
                self.setUp()
                self.state.soc_blocked = True
                sunny = replace(self.snapshot, soc=soc, pv=100, generation_forecast=2000)
                self.assertEqual(self.decide(0, sunny).action, "start")
                self.assertEqual(self.decide(1, sunny).action, "continue")
                cloudy = replace(sunny, generation_forecast=500)
                self.assertFalse(self.decide(2, cloudy).energy_allowed)

    def test_low_soc_insufficient_forecast_does_not_start(self):
        for forecast in (None, 1000, float("nan"), -1):
            with self.subTest(forecast=forecast):
                self.setUp()
                result = self.decide(0, replace(self.snapshot, soc=20, pv=100,
                                              generation_forecast=forecast))
                self.assertEqual(result.action, "wait")
                self.assertFalse(result.energy_allowed)

    def test_soc_recovery_keeps_minimum_off_deadline(self):
        self.observed = policy.ObservedDeviceState(running=True, last_start=0)
        self.state = policy.PolicyState()
        self.decide(1, replace(self.snapshot, soc=84, pv=0))
        self.decide(2, replace(self.snapshot, soc=90))
        result = self.decide(62, replace(self.snapshot, soc=90))
        self.assertEqual(result.reason, "minimum_off")
        self.assertEqual(result.seconds_to_start, 59)
        self.assertEqual(self.decide(121, replace(self.snapshot, soc=90)).action, "start")

    def test_soc_block_survives_restore_and_missing_measurement(self):
        self.decide(0, replace(self.snapshot, soc=84, pv=0))
        saved = storage.serialize(self.observed, self.state)
        self.observed = policy.ObservedDeviceState()
        self.state = policy.PolicyState()
        self.observed, self.state = storage.restore(saved, 10)
        self.decide(10, replace(self.snapshot, soc=None))
        self.assertTrue(self.state.soc_blocked)
        self.assertEqual(self.decide(20, replace(self.snapshot, soc=89)).reason, "solar_ready")
        self.decide(30, replace(self.snapshot, soc=90))
        self.assertFalse(self.state.soc_blocked)

    def test_grid_charging_and_discharge_ignore_soc_recovery(self):
        low = replace(self.snapshot, grid=True, soc=84, battery=500)
        self.assertTrue(self.decide(0, low).energy_allowed)
        charging = replace(low, soc=86, battery=-500)
        self.assertTrue(self.decide(200, charging).energy_allowed)
        self.assertTrue(self.state.soc_blocked)
        self.assertTrue(self.decide(201, replace(charging, battery=500)).energy_allowed)
        recovered = replace(charging, soc=90)
        self.decide(400, recovered)
        self.assertFalse(self.state.soc_blocked)
        self.assertEqual(self.decide(401, replace(recovered, battery=500)).action, "continue")

    def test_low_soc_allows_grid_heating_and_charging(self):
        grid = replace(
            self.snapshot,
            grid=True,
            soc=70,
            battery=-1000,
            grid_power=1800,
            grid_import_limit=3000,
            grid_limit_configured=True,
        )
        result = self.decide(0, grid)
        self.assertTrue(result.energy_allowed)
        self.assertEqual(result.action, "start")
        self.assertEqual(result.grid_import_margin, 300)
        self.assertEqual(self.decide(60, grid).action, "continue")

    def test_low_soc_grid_heating_ignores_retired_discharge_limit(self):
        self.cfg["max_battery_discharge"] = 0
        grid = replace(self.snapshot, grid=True, soc=70, battery=500)
        self.observed = policy.ObservedDeviceState(running=True, last_start=0)
        self.state = policy.PolicyState()
        result = self.decide(1, grid)
        self.assertEqual(result.action, "continue")
        self.assertTrue(result.energy_allowed)

    def test_grid_budget_allows_start_and_run_during_soc_recovery(self):
        grid = replace(
            self.snapshot, grid=True, soc=82, battery=488, pv=0, load=454,
            grid_power=20, grid_limit_configured=True, grid_import_limit=2000,
        )
        result = self.decide(0, grid)
        self.assertEqual(result.action, "start")
        self.assertEqual(result.energy_reason, "grid_ready")
        self.assertTrue(result.energy_allowed)
        self.assertEqual(result.grid_import_margin, 1080)
        self.assertTrue(self.state.soc_blocked)
        self.assertEqual(self.decide(1, replace(grid, soc=86)).action, "continue")
        # A running AC uses the lower threshold even with a retained SOC latch.
        result = self.decide(2, replace(grid, grid=False, soc=86))
        self.assertEqual(result.action, "continue")
        result = self.decide(3, replace(grid, grid=False, soc=84))
        self.assertEqual(result.action, "stop")
        self.assertEqual(result.energy_reason, "low_soc")

    def test_outage_running_soc_between_thresholds_ignores_recovery_latch(self):
        self.cfg.update(minimum_soc=78, restart_soc=85)
        self.state = policy.PolicyState(soc_blocked=True)
        self.observed = policy.ObservedDeviceState(running=True, last_start=0)
        for now, soc in ((1, 80), (2, 79), (3, 78)):
            self.assertEqual(self.decide(now, replace(self.snapshot, soc=soc)).action, "continue")
        self.assertEqual(self.decide(4, replace(self.snapshot, soc=77, pv=0)).reason, "low_soc")
        self.assertEqual(self.decide(200, replace(self.snapshot, soc=80)).reason, "solar_ready")

    def test_low_soc_discharge_does_not_mask_grid_budget_failures(self):
        grid = replace(
            self.snapshot, grid=True, soc=82, battery=488,
            grid_power=20, grid_limit_configured=True, grid_import_limit=2000,
        )
        for changes, reason in (
            ({"grid_power": 1101}, "grid_import_limit"),
            ({"grid_power": None}, "grid_power_unavailable"),
            ({"grid_import_limit": None}, "grid_limit_unavailable"),
        ):
            with self.subTest(reason=reason):
                result = self.decide(0, replace(grid, **changes))
                self.assertFalse(result.energy_allowed)
                self.assertEqual(result.energy_reason, reason)

    def test_missing_battery_soc_grid_or_temperature_blocks(self):
        for field in ("soc", "battery", "grid"):
            self.assertEqual(
                self.decide(0, replace(self.snapshot, **{field: None})).reason,
                "invalid_energy_data",
            )
        self.assertEqual(
            self.decide(0, replace(self.snapshot, temperature_valid=False)).reason,
            "invalid_energy_data",
        )

    def test_missing_solar_blocks_only_off_grid(self):
        for field in ("pv", "load"):
            self.observed = policy.ObservedDeviceState()
            self.state = policy.PolicyState()
            self.assertEqual(
                self.decide(0, replace(self.snapshot, **{field: None})).reason,
                "invalid_energy_data",
            )
            self.assertEqual(
                self.decide(0, replace(self.snapshot, grid=True, **{field: None})).action,
                "start",
            )

    def test_grid_short_discharge_spike_does_not_stop(self):
        grid = replace(self.snapshot, grid=True)
        self.decide(0, grid)
        peak = replace(grid, battery=500, load=4000)
        self.assertEqual(self.decide(10, peak).action, "continue")
        self.assertEqual(self.decide(20, grid).action, "continue")

    def test_grid_sustained_discharge_with_high_soc_does_not_stop(self):
        grid = replace(self.snapshot, grid=True)
        self.decide(0, grid)
        bad = replace(grid, battery=500)
        self.decide(10, bad)
        for now in (70, 610, 1800):
            result = self.decide(now, bad)
            self.assertEqual(result.action, "continue")
            self.assertEqual(result.reason, "grid_ready")
            self.assertTrue(result.energy_allowed)
            self.assertIsNone(result.seconds_to_stop)

    def test_current_deficit_is_not_hidden_by_old_surplus(self):
        self.cfg.update(shortage_delay=99999, grid_absence_delay=0)
        self.assertEqual(self.decide(0).action, "start")
        result = self.decide(1, replace(self.snapshot, load=4000))
        self.assertEqual(result.action, "stop")
        self.assertLess(result.solar_margin, 0)
        self.assertIsNone(result.average_solar_margin)

    def test_outage_timer_remains_independent_of_retired_deficit_delay(self):
        self.cfg.update(shortage_delay=600, grid_absence_delay=900)
        grid = replace(self.snapshot, grid=True)
        self.decide(0, grid)
        outage = replace(self.snapshot, pv=500)
        self.decide(100, outage)
        result = self.decide(700, outage)
        self.assertEqual(result.action, "continue")
        self.assertEqual(result.seconds_to_stop, 300)
        self.assertEqual(self.decide(1000, outage).reason, "outage_deficit")

    def test_grid_restoration_cancels_solar_deficit(self):
        self.start_solar()
        low = replace(self.snapshot, pv=500)
        self.decide(70, low)
        grid = replace(low, grid=True)
        self.assertEqual(self.decide(80, grid).reason, "minimum_off")
        self.assertIsNone(self.state.deficit_since)

    def test_off_grid_persistent_deficit_does_not_start(self):
        low = replace(self.snapshot, pv=500)
        self.decide(0, low)
        self.assertEqual(self.decide(1000, low).action, "wait")

    def test_temperature_cycle_and_minimum_off(self):
        grid = replace(self.snapshot, grid=True)
        self.decide(0, grid)
        self.assertEqual(self.decide(60, grid, demand=False).reason, "temperature_maintenance")
        self.assertEqual(self.decide(120, grid, demand=False).action, "continue")
        self.assertEqual(self.decide(121, grid).action, "continue")
        self.assertEqual(self.decide(240, grid).action, "continue")

    def test_manual_schedule_disabled(self):
        self.assertEqual(self.decide(0, manual=True).reason, "manual_pause")
        self.assertEqual(self.decide(0, enabled=False).reason, "disabled")
        self.assertEqual(
            self.decide(0, replace(self.snapshot, schedule_allowed=False)).reason,
            "outside_schedule",
        )

    def test_inclusive_house_load_and_charge_counted_once(self):
        self.cfg["load_includes_battery_charging"] = True
        snapshot = replace(self.snapshot, load=1600, battery=-1000)
        self.assertEqual(self.decide(0, snapshot).solar_margin, 1300)
        self.assertEqual(
            self.decide(0, replace(snapshot, battery=-2000)).reason, "invalid_energy_data"
        )

    def test_actual_ac_load_is_subtracted_only_once(self):
        self.start_solar()
        self.assertEqual(self.decide(61).solar_margin, 1300)
        actual = replace(self.snapshot, load=1500, actual_ac_power=900)
        self.assertEqual(self.decide(62, actual).solar_margin, 1300)

    def test_restore_requalifies_history_and_retains_cycle_timing(self):
        self.start_solar()
        saved = storage.serialize(self.observed, self.state)
        self.assertNotIn("window", saved)
        observed, new = storage.restore(saved, 100)
        self.assertTrue(observed.running)
        self.assertEqual(observed.last_start, 0)
        self.assertFalse(new.window.samples)

    def test_invalid_future_timestamps_not_restored(self):
        self.observed, self.state = storage.restore({"running": True, "last_start": 500}, 100)
        self.assertFalse(self.observed.running)

    def test_retired_discharge_block_is_ignored_after_upgrade(self):
        self.observed, self.state = storage.restore(
            {"discharge_blocked": True, "adverse_since": 0}, 2000
        )
        bad = replace(self.snapshot, grid=True, soc=98, battery=500)
        self.assertEqual(self.decide(2000, bad).action, "start")
        self.assertEqual(self.decide(4000, bad).action, "continue")

    def test_off_grid_discharge_alone_does_not_override_solar_balance(self):
        bad = replace(self.snapshot, battery=500)
        self.decide(0, bad)
        self.assertEqual(self.decide(60, bad).action, "continue")
        self.assertEqual(self.decide(1800, bad).action, "continue")

    def test_grid_permission_is_independent_of_operational_gates(self):
        grid = replace(self.snapshot, grid=True, pv=None, load=None)
        for kwargs, reason in (
            ({"enabled": False}, "disabled"),
            ({"manual": True}, "manual_pause"),
        ):
            self.observed = policy.ObservedDeviceState()
            self.state = policy.PolicyState()
            result = self.decide(0, grid, **kwargs)
            self.assertEqual(result.reason, reason)
            self.assertTrue(result.energy_allowed)
            self.assertEqual(result.energy_reason, "grid_ready")
            self.assertFalse(result.intent.running)
        for snapshot in (
            replace(grid, schedule_allowed=False),
            replace(grid, temperature_valid=False),
        ):
            result = self.decide(0, snapshot)
            self.assertTrue(result.energy_allowed)
            self.assertFalse(result.intent.running)

    def test_manual_pause_still_prevents_grid_start_without_discharge_rule(self):
        grid = replace(self.snapshot, grid=True, soc=84, battery=500)
        self.decide(0, grid, manual=True)
        self.decide(30, grid, manual=True)
        result = self.decide(60, grid, manual=True)
        self.assertTrue(result.energy_allowed)
        self.assertFalse(result.intent.running)

    def test_missing_ac_meter_blocks_only_off_grid_energy_permission(self):
        result = self.decide(0, replace(self.snapshot, ac_power_valid=False))
        self.assertFalse(result.energy_allowed)
        result = self.decide(0, replace(self.snapshot, grid=True, ac_power_valid=False))
        self.assertTrue(result.energy_allowed)

    def test_grid_limit_reserves_ac_start_without_discarding_charging_load(self):
        grid = replace(
            self.snapshot,
            grid=True,
            grid_power=2500,
            battery=-1500,
            grid_import_limit=3000,
            grid_limit_configured=True,
        )
        result = self.decide(0, grid)
        self.assertEqual(result.action, "wait")
        self.assertFalse(result.energy_allowed)
        self.assertEqual(result.energy_reason, "grid_import_limit")
        self.assertEqual(result.grid_import_margin, -400)

    def test_running_ac_is_not_added_to_grid_power_twice(self):
        self.observed = policy.ObservedDeviceState(running=True, last_start=0)
        self.state = policy.PolicyState()
        grid = replace(
            self.snapshot,
            grid=True,
            grid_power=2800,
            grid_import_limit=3000,
            grid_limit_configured=True,
        )
        result = self.decide(1, grid)
        self.assertEqual(result.action, "continue")
        self.assertEqual(result.grid_import_margin, 200)
        result = self.decide(2, replace(grid, grid_power=3100))
        self.assertEqual(result.action, "stop")
        self.assertEqual(result.energy_reason, "grid_import_limit")

    def test_grid_export_contributes_to_start_headroom(self):
        grid = replace(
            self.snapshot,
            grid=True,
            grid_power=-500,
            grid_import_limit=400,
            grid_limit_configured=True,
        )
        result = self.decide(0, grid)
        self.assertEqual(result.action, "start")
        self.assertEqual(result.grid_import_margin, 0)

    def test_zero_and_unconfigured_limits_are_unlimited(self):
        for enabled in (False, True):
            self.observed = policy.ObservedDeviceState()
            self.state = policy.PolicyState()
            grid = replace(
                self.snapshot,
                grid=True,
                grid_power=None,
                grid_import_limit=0,
                grid_limit_configured=enabled,
            )
            self.assertEqual(self.decide(0, grid).action, "start")

    def test_missing_limit_or_grid_measurement_blocks_only_on_grid(self):
        grid = replace(
            self.snapshot,
            grid=True,
            grid_power=0,
            grid_import_limit=None,
            grid_limit_configured=True,
        )
        self.assertEqual(self.decide(0, grid).energy_reason, "grid_limit_unavailable")
        self.assertEqual(
            self.decide(0, replace(grid, grid_import_limit=3000, grid_power=None)).energy_reason,
            "grid_power_unavailable",
        )
        self.assertEqual(self.decide(0, replace(grid, grid=False)).reason, "solar_ready")
