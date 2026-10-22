"""Group public metrics, privacy and complete translation contracts."""

import importlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from test_allocator import a, groups, models
from test_flow_logic import flow_module

view = importlib.import_module("scm_adapter_test.group_presentation")
presentation = importlib.import_module("scm_adapter_test.presentation")
flow = importlib.import_module(flow_module.GroupOptionsMixin.__module__)


class GroupPresentationTests(unittest.TestCase):
    def setUp(self):
        self.policy = groups.GroupPolicy()
        self.snapshot = a.GroupSnapshot(
            "group",
            1000,
            models.EnergySnapshot(pv=1600, load=600, battery=0, soc=95, grid=False),
            (a.DeviceRequest("a"), a.DeviceRequest("b")),
            1000,
        )

    def test_proposals_do_not_become_committed_power(self):
        result = a.allocate(self.snapshot, a.AllocationState("group"), self.policy, shadow=False)
        state = view.group_metrics(self.snapshot, result, self.policy)
        self.assertEqual(
            state,
            {"group_available_power": 1000, "group_load_power": 600, "group_reserved_power": 0},
        )
        pending = a.command_dispatched(result.state, "a", 1000)
        result = a.allocate(self.snapshot, pending, self.policy, shadow=False)
        state = view.group_metrics(self.snapshot, result, self.policy)
        self.assertEqual(state["group_available_power"], 100)
        self.assertEqual(state["group_reserved_power"], 900)

    def test_unlimited_grid_has_no_invented_numeric_headroom(self):
        snapshot = replace(self.snapshot, energy=replace(self.snapshot.energy, grid=True))
        result = a.allocate(snapshot, a.AllocationState("group"), self.policy, shadow=False)
        self.assertIsNone(
            view.group_metrics(snapshot, result, self.policy)["group_available_power"]
        )

    def test_excluded_members_and_battery_charging_count_once(self):
        policy = replace(
            self.policy, load_scope="excludes_all_members", load_includes_battery_charging=True
        )
        snapshot = replace(
            self.snapshot,
            energy=replace(self.snapshot.energy, load=1000, battery=-400),
            requests=(replace(self.snapshot.requests[0], measured_watts=300),),
        )
        result = a.allocate(snapshot, a.AllocationState("group"), policy, shadow=False)
        self.assertEqual(view.group_metrics(snapshot, result, policy)["group_load_power"], 900)

    def test_group_name_is_not_exported(self):
        data = {"group_name": "Private home name", "group_reserved_power": 900}
        exported = presentation.build_export({}, data, None, None)
        self.assertNotIn("Private home name", json.dumps(exported))
        self.assertEqual(data["group_name"], "Private home name")
        self.assertEqual(exported["decision"]["group_reserved_power"], 900)

    def test_confirmed_command_does_not_block_edit_after_observation_switch(self):
        attempt = SimpleNamespace(confirmed_at=100)
        coordinator = SimpleNamespace(
            settings={"operation_mode": "observation"},
            commands=SimpleNamespace(
                task=None, state=SimpleNamespace(unconfirmed_start=True, attempt=attempt)
            ),
        )
        entry = SimpleNamespace(
            entry_id="entry", data={"device_id": "device"}, runtime_data=coordinator
        )
        hass = SimpleNamespace(
            data={}, config_entries=SimpleNamespace(async_entries=lambda domain: [entry])
        )
        flow.ensure_editable(hass, groups.GroupRegistry(), {"device"})
        attempt.confirmed_at = None
        with self.assertRaisesRegex(ValueError, "command_in_progress"):
            flow.ensure_editable(hass, groups.GroupRegistry(), {"device"})

    def test_group_name_fits_home_assistant_state_limit(self):
        self.assertEqual(flow.group_name(" House "), "House")
        for name in ("   ", "x" * 256):
            with self.assertRaises(ValueError):
                flow.group_name(name)

    def test_priority_never_silently_truncates(self):
        self.assertEqual(flow.priority(2.0), 2)
        for value in (-1, 1.5, True, float("nan"), "3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                flow.priority(value)

    def test_all_public_enums_and_group_forms_have_both_translations(self):
        root = Path(__file__).resolve().parents[2] / "custom_components/solar_climate_manager"
        strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
        for language in ("en", "uk"):
            content = json.loads(
                (root / "translations" / f"{language}.json").read_text(encoding="utf-8")
            )
            if language == "en":
                self.assertEqual(content, strings)
            for key, options in (
                ("group_action", view.GROUP_ACTIONS),
                ("group_reason", view.GROUP_REASONS),
                ("group_command_status", view.COMMAND_PHASES),
            ):
                self.assertEqual(set(content["entity"]["sensor"][key]["state"]), set(options))
            for step in (
                "group",
                "group_create",
                "group_join",
                "group_sources",
                "group_policy",
                "group_member",
                "group_leave",
                "group_delete",
            ):
                self.assertIn(step, content["options"]["step"])
            self.assertIn("reconfigure", content["config"]["step"])
