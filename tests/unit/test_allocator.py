"""Allocation invariants, uncertain commands and shared-meter accounting."""

import importlib
import random
import unittest
from dataclasses import replace

from test_groups import groups

a = importlib.import_module("scm_adapter_test.domain.allocator")
models = importlib.import_module("scm_adapter_test.domain.types")


class AllocatorTests(unittest.TestCase):
    def setUp(self):
        self.policy = groups.GroupPolicy(grid_absence_delay=120)
        self.requests = (a.DeviceRequest("a"), a.DeviceRequest("b"))
        self.energy = models.EnergySnapshot(pv=1600, load=600, soc=95, battery=0, grid=False)
        self.snapshot = a.GroupSnapshot("group", 1000, self.energy, self.requests, 1000)
        self.state = a.AllocationState("group")

    def run_allocation(self, **changes):
        return a.allocate(replace(self.snapshot, **changes), self.state, self.policy)

    def actions(self, result):
        return {d.device_id: (d.action, d.reason) for d in result.decisions}

    def test_fresh_identical_off_report_confirms_stop_without_state_change(self):
        request = replace(self.requests[0], measured_watts=0, power_reported_at=1001,
                          state_reported_at=900, state_observed_at=1001)
        snapshot = replace(self.snapshot, now=1002, requests=(request,), load_reported_at=1001)
        state = replace(self.state, reservations=(
            a.Reservation("a", 900, 980, phase="uncertain", sent_at=990, stop_sent_at=1000),))
        settled, pending, _ = a.reconcile(snapshot, state, self.policy)
        self.assertEqual(settled.reservations, ())
        self.assertEqual(pending, 0)
        stale = replace(snapshot, requests=(replace(request, state_observed_at=999),))
        retained, pending, _ = a.reconcile(stale, state, self.policy)
        self.assertEqual(retained.reservations, state.reservations)
        self.assertEqual(pending, 900)

    def test_outdoor_guard_is_individual_and_overrides_minimum_run(self):
        for reason in ("low_outdoor_temperature", "outdoor_temperature_unavailable"):
            for running in (True, False):
                with self.subTest(reason=reason, running=running):
                    blocked = replace(self.requests[0], running=running,
                                      last_start=999, outdoor_block_reason=reason)
                    result = self.run_allocation(
                        energy=replace(self.energy, grid=True, load=1500),
                        requests=(blocked, self.requests[1]),
                    )
                    actions = self.actions(result)
                    self.assertEqual(actions["a"], ("stop" if running else "wait", reason))
                    self.assertEqual(
                        actions["b"],
                        ("wait", "telemetry_unsettled") if running else ("start", "grid_ready"),
                    )

    def test_two_900w_requests_share_1000w_atomically(self):
        result = self.run_allocation()
        self.assertEqual(
            self.actions(result),
            {"a": ("start", "solar_ready"), "b": ("wait", "insufficient_budget")},
        )
        self.assertEqual(result.shadow_reserved_watts, 900)
        self.assertEqual(result.reserved_watts, 0)
        self.assertEqual(result.available_watts, 100)
        self.assertEqual(self.state.reservations, ())
        repeated = a.allocate(self.snapshot, result.state, self.policy)
        self.assertEqual(repeated.shadow_reserved_watts, 900)
        self.assertEqual(repeated.reserved_watts, 0)
        self.assertFalse(any(d.action == "start" for d in repeated.decisions))
        with self.assertRaises(ValueError):
            a.allocate(self.snapshot, result.state, self.policy, shadow=False)

    def test_low_soc_discharge_uses_shared_grid_budget(self):
        energy = replace(
            self.energy, grid=True, soc=82, battery=488, pv=0, load=454,
            grid_power=20, grid_limit_configured=True, grid_import_limit=1000,
        )
        result = self.run_allocation(energy=energy, grid_reported_at=1000)
        self.assertEqual(
            self.actions(result),
            {"a": ("start", "grid_ready"), "b": ("wait", "insufficient_budget")},
        )
        self.assertTrue(result.state.soc_blocked)
        self.assertEqual(result.available_watts, 80)
        self.assertEqual(result.shadow_reserved_watts, 900)

    def test_low_soc_discharge_preserves_invalid_grid_budget_checks(self):
        energy = replace(
            self.energy, grid=True, soc=82, battery=488,
            grid_power=20, grid_limit_configured=True, grid_import_limit=2000,
        )
        for changes, reason in (
            ({"grid_power": None}, "grid_power_unavailable"),
            ({"grid_import_limit": None}, "grid_limit_unavailable"),
        ):
            with self.subTest(reason=reason):
                result = self.run_allocation(energy=replace(energy, **changes))
                self.assertEqual(self.actions(result)["a"], ("wait", reason))

    def test_running_member_uses_lower_soc_threshold_with_recovery_latch(self):
        self.policy = replace(self.policy, minimum_soc=78, restart_soc=85)
        self.state = replace(self.state, soc_blocked=True)
        running = replace(self.requests[0], running=True, measured_watts=900, last_start=900)
        for soc in (80, 79, 78):
            with self.subTest(soc=soc):
                result = self.run_allocation(
                    requests=(running, self.requests[1]),
                    energy=replace(self.energy, soc=soc, load=1000, pv=3000),
                )
                self.assertEqual(self.actions(result)["a"], ("continue", "running"))
                self.assertEqual(self.actions(result)["b"], ("wait", "soc_recovery"))
        result = self.run_allocation(requests=(running,), energy=replace(self.energy, soc=77))
        self.assertEqual(self.actions(result)["a"], ("stop", "low_soc"))

    def test_low_soc_grid_running_member_still_obeys_limit_and_outage(self):
        running = replace(self.requests[0], running=True, measured_watts=900, last_start=999)
        energy = replace(
            self.energy, grid=True, soc=82, battery=488, load=1400,
            grid_power=920, grid_limit_configured=True, grid_import_limit=2000,
        )
        result = self.run_allocation(requests=(running,), energy=energy)
        self.assertEqual(self.actions(result)["a"][0], "continue")
        for changes, reason in (
            ({"grid_power": 2001}, "grid_import_limit"),
            ({"grid": False}, "low_soc"),
        ):
            with self.subTest(reason=reason):
                stopped = self.run_allocation(
                    requests=(running,), energy=replace(energy, **changes),
                )
                self.assertEqual(self.actions(stopped)["a"], ("stop", reason))

    def test_low_soc_discharge_does_not_block_unlimited_grid(self):
        energy = replace(self.energy, grid=True, soc=70, battery=5000)
        for configured in (False, True):
            result = self.run_allocation(energy=replace(
                energy, grid_limit_configured=configured, grid_import_limit=0,
            ))
            self.assertEqual(self.actions(result)["a"][0], "start")

    def test_priority_is_deterministic_and_request_order_independent(self):
        result = self.run_allocation(requests=(self.requests[1], self.requests[0]))
        self.assertEqual(result, self.run_allocation())
        result = self.run_allocation(
            requests=(self.requests[0], replace(self.requests[1], priority=10))
        )
        self.assertEqual(self.actions(result)["b"][0], "start")
        self.assertEqual(self.actions(result)["a"][0], "wait")

    def test_randomized_grants_never_exceed_available_budget(self):
        rng = random.Random(62026)
        for _ in range(500):
            budget = rng.uniform(0, 6000)
            requests = tuple(
                a.DeviceRequest(
                    str(i),
                    groups.MemberPolicy(estimated_ac_power=rng.uniform(100, 2000)),
                    priority=rng.randrange(4),
                )
                for i in range(8)
            )
            result = self.run_allocation(
                energy=replace(self.energy, pv=600 + budget), requests=requests
            )
            self.assertLessEqual(sum(d.reserved_watts for d in result.decisions), budget + 1e-9)
            self.assertGreaterEqual(result.available_watts, -1e-9)
            permuted = list(requests)
            rng.shuffle(permuted)
            self.assertEqual(
                result,
                self.run_allocation(
                    energy=replace(self.energy, pv=600 + budget), requests=tuple(permuted)
                ),
            )

    def test_service_return_timeout_and_stale_aggregate_do_not_release_reserve(self):
        result = a.allocate(self.snapshot, self.state, self.policy, shadow=False)
        dispatched = a.command_dispatched(result.state, "a", 1000)
        self.assertEqual(a.command_completed(dispatched, "a"), dispatched)
        uncertain = a.command_completed(dispatched, "a", failed=True)
        self.assertEqual(uncertain.reservations[0].phase, "uncertain")
        request = replace(
            self.requests[0],
            running=True,
            measured_watts=900,
            power_reported_at=1010,
            state_reported_at=1005,
            last_start=1005,
        )
        late = replace(
            self.snapshot,
            now=1010,
            requests=(request, self.requests[1]),
            energy=replace(self.energy, load=1500),
            load_reported_at=1000,
        )
        pending = a.allocate(late, uncertain, self.policy, shadow=False)
        self.assertEqual(pending.reserved_watts, 900)
        self.assertEqual(self.actions(pending)["b"][1], "unresolved_reservation")
        settled = a.allocate(
            replace(late, load_reported_at=1010), uncertain, self.policy, shadow=False
        )
        self.assertEqual(settled.reserved_watts, 0)
        self.assertEqual(settled.state.reservations[0].phase, "accounted")
        self.assertEqual(settled.available_watts, 100)

    def test_partial_meter_accounting_charges_only_unaccounted_remainder(self):
        state = a.command_dispatched(
            a.allocate(self.snapshot, self.state, self.policy, shadow=False).state, "a", 1000
        )
        request = replace(
            self.requests[0],
            running=True,
            measured_watts=400,
            power_reported_at=1010,
            state_reported_at=1005,
            last_start=1005,
        )
        snapshot = replace(
            self.snapshot,
            now=1010,
            requests=(request,),
            energy=replace(self.energy, load=1000),
            load_reported_at=1010,
        )
        result = a.allocate(snapshot, state, self.policy, shadow=False)
        self.assertEqual(result.reserved_watts, 500)
        self.assertEqual(result.available_watts, 100)
        self.assertEqual(result.state.reservations[0].phase, "command_pending")

    def test_off_requires_explicit_stop_and_later_meter_before_release(self):
        state = a.command_dispatched(
            a.allocate(self.snapshot, self.state, self.policy, shadow=False).state, "a", 1000
        )
        state = a.command_completed(state, "a", failed=True)
        off = replace(
            self.requests[0], measured_watts=0, state_reported_at=1010, power_reported_at=1010
        )
        snapshot = replace(self.snapshot, now=1010, requests=(off,), load_reported_at=1010)
        self.assertEqual(a.allocate(snapshot, state, self.policy).reserved_watts, 900)
        stopped = a.stop_dispatched(state, "a", 1005)
        result = a.allocate(snapshot, stopped, self.policy)
        self.assertEqual(result.reserved_watts, 0)
        self.assertEqual(a.revoke_unsent(state, "a"), state)

    def test_no_meter_cannot_settle_command_or_fake_missing_configured_meter(self):
        state = a.command_dispatched(
            a.allocate(self.snapshot, self.state, self.policy, shadow=False).state, "a", 1000
        )
        running = replace(self.requests[0], running=True, state_reported_at=1005)
        snapshot = replace(
            self.snapshot,
            now=1010,
            requests=(running,),
            energy=replace(self.energy, load=1500),
            load_reported_at=1010,
        )
        self.assertEqual(a.allocate(snapshot, state, self.policy).reserved_watts, 900)
        request = replace(self.requests[0], policy=groups.MemberPolicy(ac_power_entity="sensor.ac"))
        result = self.run_allocation(requests=(request,))
        self.assertIsNone(result.available_watts)
        self.assertEqual(result.reason, "incomplete_members")

    def test_manual_power_consumes_budget_but_is_not_stopped(self):
        manual = replace(
            self.requests[0], running=True, operation_mode="temporary_block", measured_watts=900
        )
        result = self.run_allocation(
            requests=(manual, self.requests[1]), energy=replace(self.energy, load=1500)
        )
        self.assertEqual(self.actions(result)["a"], ("wait", "temporary_block"))
        self.assertEqual(self.actions(result)["b"][0], "wait")
        self.assertEqual(result.available_watts, 100)

    def test_load_scope_and_charging_are_accounted_once(self):
        running = replace(
            self.requests[0],
            running=True,
            measured_watts=900,
            power_reported_at=1000,
            state_reported_at=990,
        )
        snapshot = replace(
            self.snapshot,
            requests=(running, self.requests[1]),
            energy=replace(self.energy, pv=2400, load=2500, battery=-1000),
        )
        policy = replace(self.policy, load_includes_battery_charging=True)
        result = a.allocate(snapshot, self.state, policy)
        excluded = a.allocate(
            replace(snapshot, energy=replace(snapshot.energy, load=1600)),
            self.state,
            replace(policy, load_scope="excludes_all_members"),
        )
        self.assertEqual(result, excluded)
        self.assertEqual(self.actions(result)["b"][0], "start")
        self.assertEqual(result.available_watts, 0)
        invalid = a.allocate(
            replace(snapshot, energy=replace(snapshot.energy, load=500)), self.state, policy
        )
        self.assertEqual(invalid.reason, "inconsistent_load")

    def test_grid_limit_uses_import_once_and_export_adds_headroom(self):
        energy = replace(
            self.energy, grid=True, grid_limit_configured=True, grid_import_limit=1000, grid_power=0
        )
        result = self.run_allocation(energy=energy, grid_reported_at=1000)
        self.assertEqual(result.shadow_reserved_watts, 900)
        exported = self.run_allocation(
            energy=replace(energy, grid_power=-800), grid_reported_at=1000
        )
        self.assertEqual(exported.shadow_reserved_watts, 1800)
        self.assertEqual(exported.available_watts, 0)
        for value in (None, float("nan")):
            invalid = self.run_allocation(energy=replace(energy, grid_power=value))
            self.assertEqual(invalid.reason, "grid_power_unavailable")
            self.assertFalse(any(d.action == "start" for d in invalid.decisions))

    def test_waiting_priority_never_preempts_a_running_device(self):
        running = replace(self.requests[0], running=True, measured_watts=900, last_start=0)
        waiting = replace(self.requests[1], priority=100)
        result = self.run_allocation(
            requests=(running, waiting), energy=replace(self.energy, load=1500)
        )
        self.assertEqual(self.actions(result)["a"][0], "continue")
        self.assertEqual(self.actions(result)["b"][0], "wait")

    def test_grid_deficit_stops_only_required_low_priority_prefix(self):
        requests = tuple(
            a.DeviceRequest(str(i), priority=i, running=True, measured_watts=900, last_start=999)
            for i in range(3)
        )
        energy = replace(
            self.energy,
            grid=True,
            load=3300,
            grid_power=2500,
            grid_import_limit=2000,
            grid_limit_configured=True,
        )
        result = self.run_allocation(requests=requests, energy=energy, grid_reported_at=1000)
        self.assertEqual([d.device_id for d in result.decisions if d.action == "stop"], ["0"])
        self.assertEqual(result.unmet_deficit_watts, 0)

    def test_outage_deficit_waits_for_delay_and_minimum_run_unless_outage_deadline(self):
        request = replace(self.requests[0], running=True, measured_watts=900, last_start=990)
        snapshot = replace(
            self.snapshot, requests=(request,), energy=replace(self.energy, load=1500, pv=1000)
        )
        first = a.allocate(snapshot, self.state, self.policy)
        second = a.allocate(replace(snapshot, now=1060), first.state, self.policy)
        self.assertEqual(second.decisions[0].action, "continue")
        third = a.allocate(replace(snapshot, now=1120), second.state, self.policy)
        self.assertEqual(third.decisions[0].action, "stop")

    def test_grid_restoration_cancels_deficit_with_soc_between_thresholds(self):
        policy = replace(self.policy, minimum_soc=78, restart_soc=85)
        request = replace(self.requests[0], running=True, measured_watts=900, last_start=990)
        snapshot = replace(
            self.snapshot, requests=(request,),
            energy=replace(self.energy, soc=80, load=1500, pv=500),
        )
        first = a.allocate(snapshot, replace(self.state, soc_blocked=True), policy)
        self.assertEqual(first.decisions[0].action, "continue")
        self.assertEqual(first.state.deficit_since, 1000)
        restored = replace(snapshot, now=1050, energy=replace(
            snapshot.energy, grid=True, grid_limit_configured=True,
            grid_import_limit=2000, grid_power=1000,
        ))
        ready = a.allocate(restored, first.state, policy)
        self.assertIsNone(ready.state.deficit_since)
        self.assertIsNone(ready.state.grid_absent_since)
        later = a.allocate(replace(restored, now=1200), ready.state, policy)
        self.assertEqual(later.decisions[0].action, "continue")

    def test_low_soc_overrides_minimum_run_even_with_missing_member(self):
        running = replace(self.requests[0], running=True, measured_watts=900, last_start=999)
        result = self.run_allocation(
            requests=(running, replace(self.requests[1], available=False)),
            energy=replace(self.energy, soc=40, load=1500),
        )
        self.assertEqual(self.actions(result)["a"], ("stop", "low_soc"))
        state = result.state
        recovery = a.allocate(
            replace(self.snapshot, energy=replace(self.energy, soc=88)), state, self.policy
        )
        self.assertEqual(recovery.reason, "soc_recovery")
        ready = a.allocate(self.snapshot, recovery.state, self.policy)
        self.assertFalse(ready.state.soc_blocked)

    def test_first_deficit_sheds_without_waiting_for_deficit_duration(self):
        running = replace(self.requests[0], running=True, measured_watts=900, last_start=0)
        result = self.run_allocation(
            requests=(running,), energy=replace(self.energy, pv=100, load=1500),
        )
        self.assertEqual(self.actions(result)["a"], ("stop", "outage_deficit"))

    def test_solar_starts_immediately_but_respects_minimum_off(self):
        first = a.allocate(self.snapshot, self.state, self.policy)
        self.assertEqual(first.decisions[0].action, "start")
        paused = self.run_allocation(requests=(replace(self.requests[0], last_stop=999),))
        self.assertEqual(paused.decisions[0].reason, "minimum_off")
        deficit = self.run_allocation(energy=replace(self.energy, pv=0))
        recovered = a.allocate(self.snapshot, deficit.state, self.policy)
        self.assertEqual(recovered.decisions[0].action, "start")

    def test_modes_shadow_grants_cannot_dispatch_or_enter_real_budget(self):
        requests = tuple(
            a.DeviceRequest(mode, operation_mode=mode)
            for mode in ("observation", "disabled", "temporary_block")
        )
        preview = self.run_allocation(requests=requests)
        self.assertEqual(self.actions(preview)["observation"][0], "start")
        self.assertEqual(preview.reserved_watts, 0)
        with self.assertRaises(ValueError):
            a.command_dispatched(preview.state, "observation", 1000)
        real = a.allocate(
            replace(self.snapshot, requests=requests), self.state, self.policy, shadow=False
        )
        self.assertEqual(real.state.reservations, ())

    def test_missing_or_delayed_manual_telemetry_blocks_new_starts(self):
        request = replace(
            self.requests[0],
            running=True,
            measured_watts=900,
            state_reported_at=1000,
            power_reported_at=1010,
        )
        result = self.run_allocation(
            now=1010,
            requests=(request, self.requests[1]),
            energy=replace(self.energy, load=1500, pv=2400),
        )
        self.assertEqual(self.actions(result)["b"][1], "telemetry_unsettled")
        unavailable = self.run_allocation(
            requests=(replace(self.requests[0], running=None), self.requests[1])
        )
        self.assertFalse(any(d.action == "start" for d in unavailable.decisions))

    def test_group_state_and_duplicate_requests_cannot_cross_boundaries(self):
        with self.assertRaises(ValueError):
            a.allocate(replace(self.snapshot, group_id="other"), self.state, self.policy)
        with self.assertRaises(ValueError):
            self.run_allocation(requests=(self.requests[0], self.requests[0]))

    def test_invalid_aggregate_cannot_confirm_a_reservation(self):
        state = a.command_dispatched(
            a.allocate(self.snapshot, self.state, self.policy, shadow=False).state, "a", 1000
        )
        request = replace(
            self.requests[0],
            running=True,
            measured_watts=900,
            power_reported_at=1010,
            state_reported_at=1005,
        )
        for load in (None, float("nan"), 100):
            snapshot = replace(
                self.snapshot,
                now=1010,
                requests=(request,),
                energy=replace(self.energy, load=load),
                load_reported_at=1010,
            )
            result = a.allocate(snapshot, state, self.policy)
            self.assertEqual(result.reserved_watts, 900)
            self.assertEqual(result.state.reservations[0].phase, "command_pending")

    def test_equal_priority_deficit_uses_fewest_stops(self):
        requests = tuple(
            a.DeviceRequest(str(i), running=True, measured_watts=power, last_start=0)
            for i, power in enumerate((300, 300, 800))
        )
        energy = replace(
            self.energy,
            grid=True,
            load=2000,
            grid_power=2000,
            grid_import_limit=1300,
            grid_limit_configured=True,
        )
        result = self.run_allocation(requests=requests, energy=energy)
        self.assertEqual([d.device_id for d in result.decisions if d.action == "stop"], ["2"])

    def test_grid_meter_must_catch_up_with_individual_consumption(self):
        running = replace(
            self.requests[0],
            running=True,
            measured_watts=900,
            power_reported_at=1010,
            state_reported_at=1000,
        )
        energy = replace(
            self.energy,
            grid=True,
            load=1500,
            grid_limit_configured=True,
            grid_import_limit=2000,
            grid_power=1000,
        )
        lagging = self.run_allocation(
            now=1010,
            requests=(running, self.requests[1]),
            energy=energy,
            load_reported_at=1010,
            grid_reported_at=1005,
        )
        self.assertEqual(self.actions(lagging)["b"][1], "telemetry_unsettled")
        settled = self.run_allocation(
            now=1010,
            requests=(running, self.requests[1]),
            energy=energy,
            load_reported_at=1010,
            grid_reported_at=1010,
        )
        self.assertEqual(self.actions(settled)["b"][0], "start")

    def test_missing_or_future_aggregate_timestamp_is_not_a_start_permit(self):
        for reported_at in (None, 1001, float("nan")):
            result = self.run_allocation(load_reported_at=reported_at)
            self.assertFalse(any(d.action == "start" for d in result.decisions))
            self.assertEqual(result.decisions[0].reason, "telemetry_unsettled")

    def test_maintenance_does_not_fund_another_start_before_measurement(self):
        running = replace(
            self.requests[0],
            running=True,
            measured_watts=900,
            demand=False,
            last_start=0,
            state_reported_at=900,
            power_reported_at=1000,
        )
        result = self.run_allocation(
            requests=(running, self.requests[1]), energy=replace(self.energy, load=1500)
        )
        self.assertEqual(self.actions(result)["a"], ("continue", "temperature_maintenance"))
        self.assertEqual(self.actions(result)["b"][0], "wait")
        self.assertEqual(result.available_watts, 100)

    def test_only_minimum_off_timer_delays_solar_start(self):
        request = replace(self.requests[0], last_stop=700)
        snapshot = replace(self.snapshot, requests=(request,))
        policy = self.policy
        first = a.allocate(snapshot, self.state, policy)
        self.assertEqual(first.decisions[0].reason, "minimum_off")
        ready = a.allocate(replace(snapshot, now=1600, load_reported_at=1600), first.state, policy)
        self.assertEqual(ready.decisions[0].action, "start")
