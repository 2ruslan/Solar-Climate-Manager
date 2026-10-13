"""Energy policy replay with deterministic time and independent virtual state."""

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


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.state = policy.DemoState()
        self.snapshot = policy.EnergySnapshot(
            pv=2800,
            load=600,
            soc=95,
            battery=0,
            grid_power=0,
            grid=True,
            forecasts=(2800, 2700, 2600),
        )
        self.cfg = {
            **policy.STRATEGY_DEFAULTS,
            "start_delay": 60,
            "minimum_run_time": 120,
            "minimum_off_time": 120,
            "verification_delay": 0,
            "shortage_delay": 60,
        }

    def decide(self, now=0, snapshot=None, demand=True, **kwargs):
        return policy.decide(
            snapshot or self.snapshot, self.state, self.cfg, now=now, demand=demand, **kwargs
        )

    def start(self):
        self.assertEqual(self.decide(0).reason, "start_confirmation")
        self.assertEqual(self.decide(60).action, "would_start")

    def test_surplus_qualification_and_cycle(self):
        self.start()
        self.assertEqual(self.decide(90, demand=False).reason, "minimum_run")
        self.assertEqual(self.decide(180, demand=False).action, "would_stop")
        self.assertEqual(self.decide(200).reason, "minimum_off")
        self.assertEqual(self.decide(300).action, "would_start")

    def test_short_peak_does_not_reset_observation_window(self):
        self.decide(0)
        self.assertTrue(self.decide(50, replace(self.snapshot, pv=500)).energy_allowed)
        self.assertEqual(self.decide(60).action, "would_start")

    def test_forecast_alone_cannot_start_by_default(self):
        self.assertEqual(self.decide(0, replace(self.snapshot, pv=500)).action, "wait")
        self.cfg["allow_forecast_trial"] = True
        self.cfg["start_delay"] = 0
        self.cfg["verification_delay"] = 180
        low = replace(self.snapshot, pv=500)
        self.assertEqual(self.decide(0, low).action, "wait")
        self.assertEqual(self.decide(179, low).action, "wait")
        self.assertEqual(self.decide(180, low).action, "wait")

    def test_minimum_soc_overrides_minimum_run_and_missing_forecast(self):
        self.start()
        critical = replace(self.snapshot, soc=20, forecasts=(None, None, None))
        result = self.decide(61, critical)
        self.assertEqual(result.action, "would_stop")
        self.assertEqual(result.reason, "low_soc")

    def test_missing_core_data_never_allows_start(self):
        for field in ("pv", "load", "soc", "battery", "grid_power", "grid"):
            with self.subTest(field=field):
                result = self.decide(0, replace(self.snapshot, **{field: None}))
                self.assertFalse(result.energy_allowed)
                self.assertEqual(result.reason, "invalid_energy_data")

    def test_missing_required_forecast(self):
        self.assertEqual(
            self.decide(0, replace(self.snapshot, forecasts=(2800, None, 2700))).reason,
            "invalid_energy_data",
        )
        self.cfg["require_forecast"] = False
        self.assertFalse(
            self.decide(0, replace(self.snapshot, forecasts=(None, None, None))).energy_allowed
        )

    def test_excess_discharge_has_correct_wait_reason(self):
        self.decide(0, replace(self.snapshot, battery=500))
        self.assertEqual(
            self.decide(61, replace(self.snapshot, battery=500)).reason, "battery_discharge"
        )
        self.state = policy.DemoState()
        self.decide(0, replace(self.snapshot, grid_power=500))
        self.assertEqual(
            self.decide(61, replace(self.snapshot, grid_power=500)).reason, "grid_import"
        )

    def test_paired_outage_and_deficit_timers(self):
        self.cfg.update(minimum_run_time=3600, shortage_delay=600, grid_absence_delay=600)
        self.start()
        outage = replace(self.snapshot, grid=False)
        self.assertEqual(self.decide(100, outage).action, "would_continue")
        low = replace(outage, pv=500)
        self.decide(300, low)
        self.assertEqual(self.decide(700, low).action, "would_continue")
        self.assertEqual(self.decide(900, low).reason, "outage_deficit")

    def test_outage_without_deficit_keeps_running(self):
        self.start()
        self.assertEqual(
            self.decide(1000, replace(self.snapshot, grid=False)).action, "would_continue"
        )

    def test_grid_online_does_not_authorize_unlimited_import(self):
        low = replace(self.snapshot, pv=500, grid_power=100)
        self.cfg["allow_grid_import"] = True
        self.assertFalse(self.decide(0, low).energy_allowed)
        self.cfg["max_grid_import"] = 1500
        self.assertTrue(self.decide(0, low).energy_allowed)

    def test_disabled_grid_import_does_not_use_hidden_limit(self):
        self.cfg.update(allow_grid_import=False, max_grid_import=1500)
        self.decide(0, replace(self.snapshot, grid_power=50))
        result = self.decide(61, replace(self.snapshot, grid_power=50))
        self.assertFalse(result.energy_allowed)
        self.assertEqual(result.reason, "grid_import")

    def test_charge_priority_and_discharge_limit(self):
        limited = replace(self.snapshot, pv=1900, soc=88, battery=-500)
        self.assertFalse(self.decide(0, limited).energy_allowed)
        self.cfg["prioritize_charging"] = False
        self.assertTrue(self.decide(0, limited).energy_allowed)
        self.decide(0, replace(limited, battery=200))
        self.assertEqual(self.decide(61, replace(limited, battery=200)).reason, "battery_discharge")

    def test_inclusive_load_matches_exclusive_load_without_double_counting(self):
        exclusive = replace(self.snapshot, soc=88, battery=-1000)
        baseline = self.decide(0, exclusive)
        self.cfg["load_includes_battery_charging"] = True
        inclusive = replace(exclusive, load=1600)
        result = self.decide(0, inclusive)
        self.assertEqual(result.solar_margin, baseline.solar_margin)
        self.assertEqual(result.forecast_margin, baseline.forecast_margin)

    def test_signed_charge_used_once(self):
        self.cfg["load_includes_battery_charging"] = True
        snapshot = replace(self.snapshot, load=1600, battery=-1000)
        self.assertEqual(self.decide(0, snapshot).solar_margin, 300)
        self.cfg["prioritize_charging"] = False
        snapshot = replace(snapshot, soc=88)
        self.assertEqual(self.decide(0, snapshot).solar_margin, 1300)

    def test_discharge_not_subtracted_from_load(self):
        self.cfg["load_includes_battery_charging"] = True
        self.assertEqual(policy.house_load_power(600, 0, True), 600)
        snapshot = replace(self.snapshot, battery=50)
        self.assertEqual(self.decide(0, snapshot).solar_margin, 1300)

    def test_charge_greater_than_total_is_invalid(self):
        self.cfg["load_includes_battery_charging"] = True
        self.assertEqual(
            self.decide(0, replace(self.snapshot, battery=-1000)).reason,
            "invalid_energy_data",
        )

    def test_unwanted_discharge_and_import_stop_after_confirmation(self):
        for field, reason in [("battery", "battery_discharge"), ("grid_power", "grid_import")]:
            self.state = policy.DemoState()
            self.start()
            bad = replace(self.snapshot, **{field: 500})
            self.assertEqual(self.decide(61, bad).action, "would_continue")
            self.assertEqual(self.decide(121, bad).reason, reason)

    def test_virtual_load_never_subtracted_from_real_house_load(self):
        self.start()
        before = self.decide(61).solar_margin
        self.assertEqual(before, 1300)
        self.assertEqual(self.decide(62).solar_margin, before)
        actual = replace(self.snapshot, load=1500, actual_ac_power=900)
        self.assertEqual(self.decide(63, actual).solar_margin, before)

    def test_virtual_siblings_reserve_power(self):
        self.assertFalse(
            self.decide(0, replace(self.snapshot, other_virtual_power=1800)).energy_allowed
        )

    def test_manual_disabled_and_schedule_override(self):
        self.start()
        self.assertEqual(self.decide(61, manual=True).reason, "manual_pause")
        self.assertFalse(self.state.running)
        self.assertEqual(self.decide(62, enabled=False).reason, "disabled")
        self.assertEqual(
            self.decide(63, replace(self.snapshot, schedule_allowed=False)).reason,
            "outside_schedule",
        )

    def test_restore_minimum_off_but_not_continuity(self):
        self.start()
        self.decide(180, demand=False)
        restored = policy.DemoState()
        restored.restore(policy.serialize(self.state), 200)
        self.assertEqual(restored.last_stop, 180)
        self.assertIsNone(restored.surplus_since)
        self.state = restored
        result = self.decide(200)
        self.assertEqual(result.seconds_to_start, 100)

    def test_invalid_future_timestamps_not_restored(self):
        self.state.restore({"running": True, "last_start": 500, "last_stop": float("nan")}, 100)
        self.assertFalse(self.state.running)
        self.assertIsNone(self.state.last_stop)

    def test_no_hidden_power_buffer_in_budget(self):
        self.start()
        self.assertEqual(
            self.decide(1000, replace(self.snapshot, pv=1500)).action, "would_continue"
        )

    def test_restored_running_cycle_rechecks_data(self):
        self.start()
        restored = policy.DemoState()
        restored.restore(policy.serialize(self.state), 100)
        self.state = restored
        self.assertEqual(self.decide(100, replace(self.snapshot, grid=None)).action, "would_stop")

    def test_fridge_peak_can_coincide_with_start_and_does_not_stop_cycle(self):
        self.cfg.update(start_delay=600, shortage_delay=600)
        self.decide(0)
        peak = replace(self.snapshot, load=4000, grid_power=500, battery=500)
        self.assertEqual(self.decide(590, peak).action, "wait")
        result = self.decide(600, peak)
        self.assertEqual(result.action, "would_start")
        self.assertLess(result.solar_margin, 0)
        self.assertGreater(result.average_solar_margin, 0)
        self.assertEqual(self.decide(610, peak).action, "would_continue")
        self.assertEqual(self.decide(620).action, "would_continue")

    def test_persistent_overload_prevents_start_and_stops_running(self):
        self.cfg.update(start_delay=600, shortage_delay=600)
        peak = replace(self.snapshot, load=4000, grid_power=500, battery=500)
        self.decide(0, peak)
        self.assertEqual(self.decide(600, peak).action, "wait")
        self.state = policy.DemoState()
        self.decide(0)
        self.assertEqual(self.decide(600).action, "would_start")
        self.assertEqual(self.decide(610, peak).action, "would_continue")
        self.assertEqual(self.decide(1210, peak).action, "would_stop")

    def test_restart_does_not_claim_unobserved_history(self):
        self.decide(0)
        saved = policy.serialize(self.state)
        self.assertNotIn("window", saved)
        new = policy.DemoState()
        new.restore(saved, 600)
        self.state = new
        self.assertEqual(self.decide(600).seconds_to_start, 60)

    def test_only_minimum_soc_controls_immediate_stop(self):
        self.cfg.update(critical_soc=99, battery_reserve_soc=100)
        self.start()
        self.assertEqual(self.decide(61, replace(self.snapshot, soc=84)).reason, "low_soc")

    def test_longer_outage_setting_is_not_bypassed_by_generic_deficit(self):
        self.cfg.update(shortage_delay=600, grid_absence_delay=900)
        self.start()
        outage = replace(self.snapshot, grid=False, pv=500)
        self.decide(100, outage)
        result = self.decide(700, outage)
        self.assertEqual(result.action, "would_continue")
        self.assertEqual(result.seconds_to_stop, 300)
        self.assertEqual(self.decide(1000, outage).reason, "outage_deficit")
