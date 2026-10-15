"""Group boundaries, durable uncertainty and legacy identity migration."""

import asyncio
import importlib
import json
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock

from test_coordinator import constants

groups = importlib.import_module("scm_adapter_test.domain.groups")
storage = importlib.import_module("scm_adapter_test.adapters.groups")
migrations = importlib.import_module("scm_adapter_test.adapters.migrations")
settings = importlib.import_module("scm_adapter_test.settings")


def configured_sources():
    return groups.GroupSources(
        load_power_entity="sensor.house",
        soc_entity="sensor.soc",
        battery_power_entity="sensor.battery",
        grid_available_entity="binary_sensor.grid",
    )


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.registry, self.first = groups.GroupRegistry().create(
            "House", configured_sources(), groups.GroupPolicy()
        )
        self.registry, self.second = self.registry.create(
            "Workshop", configured_sources(), groups.GroupPolicy(minimum_soc=70, restart_soc=80)
        )

    def test_two_independent_devices_are_not_automatically_grouped(self):
        for device in ("entry-one", "entry-two"):
            self.assertIsNone(self.registry.membership(device))
        self.assertEqual(self.registry.readiness(self.first, frozenset()), "no_members")

    def test_two_members_and_two_groups_have_explicit_isolated_membership(self):
        state = (
            self.registry.join("one", self.first).join("two", self.first).join("three", self.second)
        )
        self.assertEqual(state.readiness(self.first, frozenset({"one", "two"})), "configured")
        self.assertEqual(
            state.readiness(self.second, frozenset({"one", "two"})), "members_unavailable"
        )
        self.assertEqual(state.group(self.second).policy.minimum_soc, 70)
        with self.assertRaisesRegex(ValueError, "already_grouped"):
            state.join("one", self.second)
        moved = state.leave("one").join("one", self.second)
        self.assertEqual(moved.membership("one").group_id, self.second)
        self.assertEqual(state.membership("one").group_id, self.first)

    def test_reload_missing_group_and_unresolved_reserve_remain_blocked(self):
        state = self.registry.join("one", self.first)
        state = replace(state, unresolved=(groups.UnresolvedReservation("one", self.first, 900),))
        restored = groups.restore_registry(json.loads(json.dumps(groups.serialize_registry(state))))
        self.assertEqual(restored, state)
        self.assertEqual(
            restored.readiness(self.first, frozenset({"one"})), "unresolved_reservation"
        )
        self.assertEqual(restored.readiness(self.first, frozenset()), "members_unavailable")
        missing = replace(restored, groups=())
        self.assertEqual(missing.readiness(self.first, frozenset({"one"})), "missing_group")
        self.assertEqual(groups.restore_registry(groups.serialize_registry(missing)), missing)
        with self.assertRaisesRegex(ValueError, "unresolved"):
            restored.leave("one")
        with self.assertRaises(ValueError):
            restored.delete(self.first)
        orphan = replace(missing, memberships=())
        with self.assertRaisesRegex(ValueError, "unresolved"):
            orphan.join("one", self.second)
        with self.assertRaisesRegex(ValueError, "unresolved"):
            orphan.delete(self.first)

    def test_update_keeps_identity_membership_and_uncertainty(self):
        state = self.registry.join("one", self.first)
        state = replace(state, unresolved=(groups.UnresolvedReservation("one", self.first, 900),))
        changed = state.update(replace(state.group(self.first), name="Renamed"))
        self.assertEqual(changed.memberships, state.memberships)
        self.assertEqual(changed.unresolved, state.unresolved)
        self.assertEqual(changed.group(self.first).name, "Renamed")
        self.assertIsNone(self.registry.delete(self.first).group(self.first))

    def test_incomplete_sources_and_invalid_contracts_rejected(self):
        state = self.registry.join("one", self.first)
        state = state.update(replace(state.group(self.first), sources=groups.GroupSources()))
        self.assertEqual(state.readiness(self.first, frozenset({"one"})), "incomplete_sources")
        for kwargs in (
            {"minimum_soc": 90, "restart_soc": 85},
            {"max_battery_discharge": float("nan")},
            {"load_scope": "some_members"},
            {"grid_positive": "other"},
        ):
            with self.assertRaises(ValueError):
                groups.GroupPolicy(**kwargs)
        with self.assertRaises(ValueError):
            groups.GroupSources(load_power_entity="climate.ac")
        with self.assertRaises(ValueError):
            groups.MemberPolicy(estimated_ac_power=-1)

    def test_device_parameters_and_group_policy_have_separate_ownership(self):
        member = groups.MemberPolicy.from_settings(
            {
                **constants.DEFAULTS,
                "estimated_ac_power": 1200,
                "minimum_soc": 50,
                "ac_power_entity": "sensor.ac",
            }
        )
        self.assertEqual(member.estimated_ac_power, 1200)
        self.assertEqual(self.registry.group(self.first).policy.minimum_soc, 85)
        self.assertFalse(hasattr(member, "minimum_soc"))
        self.assertFalse(hasattr(self.registry.group(self.first).policy, "minimum_off_time"))

    def test_unknown_versions_corruption_and_duplicate_members_are_not_reset(self):
        self.assertEqual(groups.restore_registry(None), groups.GroupRegistry())
        valid = groups.serialize_registry(self.registry.join("one", self.first))
        invalid = [
            {},
            {**valid, "schema_version": 2},
            {**valid, "unresolved": None},
            {**valid, "memberships": [*valid["memberships"], *valid["memberships"]]},
            {**valid, "future_field": True},
        ]
        for raw in invalid:
            with self.assertRaises(ValueError):
                groups.restore_registry(raw)

    def test_migration_preserves_every_mode_options_and_policy_signature(self):
        for mode in ("control", "observation", "disabled", "temporary_block"):
            original = {
                **constants.DEFAULTS,
                "climate_entity": "climate.old",
                "operation_mode": mode,
            }
            options = {"temporary_block_date": "2026-10-15", "temporary_previous_mode": "control"}
            migrated = migrations.migrate_device_data(original, 1, "stable-entry-id")
            self.assertEqual(migrated["device_id"], "stable-entry-id")
            self.assertEqual(migrated["operation_mode"], mode)
            self.assertEqual(
                settings.configuration_values(
                    original, options, constants.DEFAULTS, constants.REMOVED_SETTINGS
                ),
                settings.configuration_values(
                    migrated, options, constants.DEFAULTS, constants.REMOVED_SETTINGS
                ),
            )
            migrated["climate_entity"] = "climate.renamed"
            self.assertEqual(
                migrations.migrate_device_data(migrated, 2, "stable-entry-id")["device_id"],
                "stable-entry-id",
            )
            self.assertNotIn("device_id", original)
        with self.assertRaises(ValueError):
            migrations.migrate_device_data({}, 3, "entry")
        with self.assertRaises(ValueError):
            migrations.migrate_device_data({}, 2, "entry")


class RepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = None

        async def save(data):
            await asyncio.sleep(0)
            self.saved = json.loads(json.dumps(data))

        self.store = AsyncMock()
        self.store.async_load.side_effect = lambda: self.saved
        self.store.async_save.side_effect = save
        self.repository = storage.GroupRepository(self.store)

    async def test_concurrent_changes_are_serialized_and_reload_preserves_both(self):
        await asyncio.gather(
            *(
                self.repository.async_update(
                    lambda state, name=name: state.create(
                        name, configured_sources(), groups.GroupPolicy()
                    )[0]
                )
                for name in ("One", "Two")
            )
        )
        restored = await storage.GroupRepository(self.store).async_load()
        self.assertEqual({g.name for g in restored.groups}, {"One", "Two"})
        self.assertEqual(restored, self.repository.registry)

    async def test_failed_save_does_not_publish_mutation(self):
        original = await self.repository.async_load()
        self.store.async_save.side_effect = OSError("disk unavailable")
        with self.assertRaises(OSError):
            await self.repository.async_update(
                lambda state: state.create("One", configured_sources(), groups.GroupPolicy())[0]
            )
        self.assertIs(self.repository.registry, original)
        self.assertIsNone(self.saved)

    async def test_corrupt_store_is_never_overwritten_on_load_or_mutation(self):
        self.saved = {"schema_version": 900}
        with self.assertRaises(ValueError):
            await self.repository.async_load()
        with self.assertRaises(ValueError):
            await self.repository.async_update(lambda state: groups.GroupRegistry())
        self.store.async_save.assert_not_awaited()
