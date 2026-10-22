"""Explicit estimation, coherent aggregates and conservative command recovery."""

import importlib
import unittest
from dataclasses import replace

from test_allocator import a, groups, models

view = importlib.import_module("scm_adapter_test.group_presentation")


class EstimatedAccountingTests(unittest.TestCase):
    def setUp(self):
        self.member = groups.MemberPolicy(power_accounting="estimated", power_settle_seconds=30)
        self.policy = groups.GroupPolicy()
        self.request = a.DeviceRequest("a", self.member, running=True,
                                       state_reported_at=1001, state_observed_at=1001,
                                       command_confirmed_at=1001, last_start=1001)
        self.snapshot = a.GroupSnapshot(
            "g", 1040, models.EnergySnapshot(pv=3000, load=800, soc=95, battery=0, grid=False),
            (self.request, a.DeviceRequest("b", self.member)), 1040)
        self.reserve = a.Reservation("a", 900, 999, phase="command_pending", sent_at=1000)
        self.state = a.AllocationState("g", (self.reserve,))

    def test_exact_estimate_reserves_capacity_before_start(self):
        snapshot = replace(self.snapshot, requests=(replace(self.request, running=False),),
                           energy=replace(self.snapshot.energy, pv=1699))
        result = a.allocate(snapshot, a.AllocationState("g"), self.policy, shadow=False)
        self.assertEqual(result.decisions[0].reason, "insufficient_budget")
        result = a.allocate(replace(snapshot, energy=replace(snapshot.energy, pv=1700)),
                            a.AllocationState("g"), self.policy, shadow=False)
        self.assertEqual(result.decisions[0].action, "start")
        self.assertEqual(result.reserved_watts, 900)

    def test_included_estimate_does_not_require_load_to_equal_estimate(self):
        # An inverter AC may consume less than its configured planning power.
        result = a.allocate(self.snapshot, self.state, self.policy, shadow=False)
        self.assertEqual(result.state.reservations[0].phase, "accounted")
        self.assertEqual(result.decisions[1].action, "start")
        self.assertEqual(result.available_watts, 1300)  # 3000 - 800 - next start 900
        self.assertEqual(view.group_metrics(self.snapshot, result, self.policy)["group_load_power"], 800)

    def test_estimate_cannot_confirm_failed_restored_or_unacknowledged_start(self):
        for reserve, request in (
            (replace(self.reserve, phase="uncertain"), self.request),
            (self.reserve, replace(self.request, command_confirmed_at=None)),
            (self.reserve, replace(self.request, command_confirmed_at=999)),
            (self.reserve, replace(self.request, running=False)),
            (replace(self.reserve, stop_sent_at=1030), self.request),
        ):
            with self.subTest(reserve=reserve, request=request):
                state, pending, _ = a.reconcile(replace(self.snapshot, requests=(request,)),
                                                replace(self.state, reservations=(reserve,)), self.policy)
                self.assertNotEqual(state.reservations[0].phase, "accounted")
                self.assertEqual(pending, 900)

    def test_stabilization_requires_new_aggregate_not_just_elapsed_time(self):
        for snapshot in (
            replace(self.snapshot, now=1020, load_reported_at=1020),
            replace(self.snapshot, load_reported_at=1031),
            replace(self.snapshot, load_reported_at=1000),
            replace(self.snapshot, complete=False),
            replace(self.snapshot, load_reported_at=1050),
        ):
            with self.subTest(snapshot=snapshot):
                _, pending, _ = a.reconcile(snapshot, self.state, self.policy)
                self.assertEqual(pending, 900)

    def test_post_stabilization_report_does_not_expire(self):
        snapshot = replace(self.snapshot, now=100000)
        state, pending, _ = a.reconcile(snapshot, self.state, self.policy)
        self.assertEqual(pending, 0)
        self.assertEqual(state.reservations[0].phase, "accounted")

    def test_grid_limit_requires_post_stabilization_grid_report(self):
        snapshot = replace(self.snapshot, energy=replace(self.snapshot.energy, grid=True,
                           grid_limit_configured=True, grid_import_limit=4000, grid_power=1200),
                           grid_reported_at=1020)
        _, pending, _ = a.reconcile(snapshot, self.state, self.policy)
        self.assertEqual(pending, 900)
        state, pending, _ = a.reconcile(replace(snapshot, grid_reported_at=1040), self.state, self.policy)
        self.assertEqual(pending, 0)
        self.assertEqual(state.reservations[0].phase, "accounted")

    def test_excluded_pending_and_settled_estimate_charged_once(self):
        policy = replace(self.policy, load_scope="excludes_all_members")
        snapshot = replace(self.snapshot, requests=(self.request,))
        for current in (snapshot, replace(snapshot, load_reported_at=1020)):
            with self.subTest(report=current.load_reported_at):
                result = a.allocate(current, self.state, policy, shadow=False)
                self.assertEqual(result.available_watts, 1300)
                metrics = view.group_metrics(current, result, policy)
                self.assertEqual(metrics["group_load_power"] + metrics["group_reserved_power"], 1700)

    def test_uncertain_estimate_needs_explicit_off_and_fresh_settled_load(self):
        state = replace(self.state, reservations=(replace(self.reserve, phase="uncertain", stop_sent_at=1005),))
        request = replace(self.request, running=False, state_reported_at=900, state_observed_at=1010)
        snapshot = replace(self.snapshot, requests=(request,))
        settled, pending, _ = a.reconcile(snapshot, state, self.policy)
        self.assertEqual(settled.reservations, ())
        self.assertEqual(pending, 0)
        for stale in (replace(snapshot, load_reported_at=1030),
                      replace(snapshot, requests=(replace(request, state_observed_at=1004),))):
            _, pending, _ = a.reconcile(stale, state, self.policy)
            self.assertEqual(pending, 900)
        _, pending, _ = a.reconcile(snapshot, self.state, self.policy)
        self.assertEqual(pending, 900)  # Off without dispatch is not proof.

    def test_manual_estimated_start_waits_for_stabilization(self):
        result = a.allocate(replace(self.snapshot, load_reported_at=1020), a.AllocationState("g"), self.policy)
        self.assertEqual(result.decisions[1].reason, "telemetry_unsettled")

    def test_mixed_group_accepts_old_meter_without_inventing_estimated_measurement(self):
        measured = a.DeviceRequest("meter", groups.MemberPolicy(ac_power_entity="sensor.ac"),
                                  running=True, measured_watts=500, power_reported_at=1040,
                                  state_reported_at=900)
        snapshot = replace(self.snapshot, requests=(self.request, measured))
        _, pending, _ = a.reconcile(snapshot, self.state, self.policy)
        self.assertEqual(pending, 0)
        stale = replace(snapshot, requests=(self.request, replace(measured, power_reported_at=1)))
        _, pending, _ = a.reconcile(stale, self.state, self.policy)
        self.assertEqual(pending, 0)

    def test_legacy_reservation_is_not_automatically_converted(self):
        request = replace(self.request, policy=replace(self.member, power_accounting="legacy"))
        _, pending, _ = a.reconcile(replace(self.snapshot, requests=(request,)), self.state, self.policy)
        self.assertEqual(pending, 900)

    def test_estimated_mode_ignores_retained_unused_meter(self):
        request = replace(self.request, measured_watts=float("nan"), power_reported_at=1,
                          policy=replace(self.member, ac_power_entity="sensor.old"))
        self.assertEqual(request.watts, 900)
        _, pending, _ = a.reconcile(replace(self.snapshot, requests=(request,)), self.state, self.policy)
        self.assertEqual(pending, 0)

    def test_retired_margin_does_not_change_planned_power(self):
        for margin in (0, 20, 100):
            policy = groups.MemberPolicy.from_settings({
                "power_accounting": "estimated", "estimated_ac_power": 1200,
                "power_margin_percent": margin,
            })
            self.assertEqual(policy.planned_watts, 1200)

    def test_policy_validation_and_meterless_legacy_fallback(self):
        self.assertEqual(groups.MemberPolicy.from_settings({}).power_accounting, "estimated")
        self.assertEqual(groups.MemberPolicy.from_settings({}).planned_watts, 900)
        for update in ({"power_accounting": "unknown"}, {"power_accounting": "meter"},
                       {"power_settle_seconds": 0},
                       {"power_settle_seconds": True}, {"estimated_ac_power": 0}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                groups.MemberPolicy.from_settings(update)

    def test_legacy_without_meter_recovers_existing_stop_then_starts(self):
        member = groups.MemberPolicy.from_settings({
            "power_accounting": "legacy", "estimated_ac_power": 1000,
            "power_settle_seconds": 30, "minimum_off_time": 0,
        })
        request = replace(self.request, policy=member, running=False,
                          command_confirmed_at=None, state_observed_at=1010)
        reserve = replace(self.reserve, watts=1000, phase="uncertain", stop_sent_at=1005)
        state = replace(self.state, reservations=(reserve,))
        energy = replace(self.snapshot.energy, grid=True, soc=81, pv=1810, load=687,
                         grid_limit_configured=True, grid_import_limit=2000, grid_power=86)
        snapshot = replace(self.snapshot, requests=(request,), energy=energy,
                           grid_reported_at=1040)
        result = a.allocate(snapshot, state, self.policy, shadow=False)
        self.assertEqual(result.decisions[0].action, "start")
        self.assertEqual(result.reserved_watts, 1000)  # Old reserve released, new one admitted.
        self.assertEqual(result.available_watts, 914)
        for stale in (replace(snapshot, load_reported_at=1030),
                      replace(snapshot, grid_reported_at=1030),
                      replace(snapshot, requests=(replace(request, state_observed_at=1004),))):
            with self.subTest(snapshot=stale):
                self.assertEqual(a.allocate(stale, state, self.policy).decisions[0].action, "wait")

    def test_legacy_configured_meter_never_falls_back_when_missing(self):
        member = groups.MemberPolicy.from_settings({
            "power_accounting": "legacy", "ac_power_entity": "sensor.ac",
        })
        self.assertEqual(member.power_accounting, "legacy")
        request = replace(self.request, policy=member, measured_watts=None)
        result = a.allocate(replace(self.snapshot, requests=(request,)), self.state, self.policy)
        self.assertEqual(result.reason, "incomplete_members")

    def test_starts_use_only_current_capacity(self):
        request = replace(self.request, running=False)
        for grid in (False, True):
            energy = replace(self.snapshot.energy, grid=grid, pv=3000, load=800,
                             grid_limit_configured=True, grid_import_limit=3000, grid_power=800)
            snapshot = replace(self.snapshot, requests=(request,), energy=energy,
                               grid_reported_at=1040)
            result = a.allocate(snapshot, a.AllocationState("g"), self.policy, shadow=False)
            self.assertEqual(result.decisions[0].action, "start")
            # Insufficient current headroom blocks a start.
            result = a.allocate(replace(snapshot, energy=replace(
                energy, pv=1000, grid_power=2800)),
                a.AllocationState("g"), self.policy, shadow=False)
            self.assertEqual(result.decisions[0].reason, "insufficient_budget")
