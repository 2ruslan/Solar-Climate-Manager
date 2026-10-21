"""Group UI, identity preservation and public entity contracts in real HA."""

from dataclasses import asdict, replace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.helpers import entity_registry as er
from test_integration import enable_group_control, grouped_input, setup, setup_shadow_group

from custom_components.solar_climate_manager.adapters.groups import get_group_repository
from custom_components.solar_climate_manager.const import DOMAIN
from custom_components.solar_climate_manager.domain.groups import GroupPolicy, UnresolvedReservation
from custom_components.solar_climate_manager.group_flow import GROUP_FLAGS, POLICY_KEYS


async def options(hass, entry, step):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    if step in ("group", "learning_reset"):
        return await hass.config_entries.options.async_configure(
            result["flow_id"], {**grouped_input(entry), "settings_action": step}
        )
    result["_test_entry"] = entry
    return result


async def group_form(hass, entry, step):
    result = await options(hass, entry, "group")
    assert result["type"] == "menu"
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def submit(hass, form, values):
    if form["step_id"] == "init":
        values = grouped_input(form["_test_entry"], **values)
    return await hass.config_entries.options.async_configure(form["flow_id"], values)


async def test_shared_settings_save_sources_and_policy_together(hass):
    first, _, repository, group_id = await setup_shadow_group(hass)
    before = repository.registry.group(group_id)
    form = await group_form(hass, first, "group_settings")
    values = {**asdict(before.sources), **asdict(before.policy)}
    values = {key: value for key, value in values.items() if value is not None}
    values.update(minimum_soc=70, restart_soc=80, grid_on_means_available=False)
    values.pop("pv_power_entity")
    result = await submit(hass, form, values)
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    after = repository.registry.group(group_id)
    assert after.sources.pv_power_entity is None
    assert after.policy.minimum_soc == 70
    assert after.policy.restart_soc == 80
    assert after.policy.grid_on_means_available is False
    assert after.sources.load_power_entity == before.sources.load_power_entity


async def test_shared_settings_reject_stale_form_and_invalid_thresholds(hass):
    first, _, repository, group_id = await setup_shadow_group(hass)
    before = repository.registry.group(group_id)
    old = await group_form(hass, first, "group_settings")
    new = await group_form(hass, first, "group_settings")
    values = {key: value for key, value in
              {**asdict(before.sources), **asdict(before.policy)}.items() if value is not None}
    invalid = await submit(hass, new, {**values, "minimum_soc": 90, "restart_soc": 80})
    assert invalid["errors"]["base"] == "invalid_soc_thresholds"
    assert repository.registry.group(group_id) == before
    saved = await submit(hass, invalid, {**values, "minimum_soc": 70})
    assert saved["type"] == "create_entry"
    await hass.async_block_till_done()
    stale = await submit(hass, old, {**values, "minimum_soc": 60})
    assert stale["errors"]["base"] == "configuration_changed"
    assert repository.registry.group(group_id).policy.minimum_soc == 70


def group_sources():
    return {
        "pv_power_entity": "sensor.pv",
        "load_power_entity": "sensor.load",
        "soc_entity": "sensor.soc",
        "battery_power_entity": "sensor.battery",
        "grid_available_entity": "binary_sensor.grid",
        **{k: v for k, v in asdict(GroupPolicy()).items() if k in GROUP_FLAGS | {"load_scope"}},
    }


def policy(**updates):
    return {**{k: v for k, v in asdict(GroupPolicy()).items() if k in POLICY_KEYS}, **updates}


def energy(hass):
    for entity, value, unit in (
        ("sensor.pv", "1600", "W"),
        ("sensor.load", "600", "W"),
        ("sensor.soc", "95", "%"),
        ("sensor.battery", "0", "W"),
    ):
        hass.states.async_set(entity, value, {"unit_of_measurement": unit})
    hass.states.async_set("binary_sensor.grid", "off")


async def test_group_wizard_is_atomic_and_preserves_modes_and_identity(hass):
    entry = await setup(hass)
    energy(hass)
    identity = entry.runtime_data.device_id
    old_options = dict(entry.options)
    repository = get_group_repository(hass)
    with patch.object(type(hass.services), "async_call") as calls:
        form = await group_form(hass, entry, "group_create")
        form = await submit(hass, form, {"name": "House", "priority": 7})
        assert form["step_id"] == "group_sources"
        assert repository.registry.groups == ()
        form = await submit(hass, form, group_sources())
        assert form["step_id"] == "group_policy"
        assert repository.registry.groups == ()
        result = await submit(hass, form, policy(start_delay=0))
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        calls.assert_not_called()
    assert dict(entry.options) == old_options
    assert entry.runtime_data.device_id == identity
    assert entry.runtime_data.settings["operation_mode"] == "observation"
    assert repository.registry.membership(identity).priority == 7
    assert repository.registry.groups[0].name == "House"
    assert entry.runtime_data.data["group_name"] == "House"
    assert entry.runtime_data.data["group_action"] == "preview_start"


async def test_group_wizard_rejects_incomplete_sources_and_invalid_soc(hass):
    entry = await setup(hass)
    energy(hass)
    form = await group_form(hass, entry, "group_create")
    form = await submit(hass, form, {"name": "House", "priority": 0})
    sources = group_sources()
    sources.pop("load_power_entity")
    form = await submit(hass, form, sources)
    assert form["errors"]["base"] == "incomplete_sources"
    form = await submit(hass, form, group_sources())
    form = await submit(hass, form, policy(minimum_soc=90, restart_soc=90))
    assert form["errors"]["base"] == "invalid_soc_thresholds"
    assert get_group_repository(hass).registry.groups == ()


async def test_group_wizard_storage_failure_keeps_registry_unchanged(hass):
    entry = await setup(hass)
    energy(hass)
    form = await group_form(hass, entry, "group_create")
    form = await submit(hass, form, {"name": "House", "priority": 0})
    form = await submit(hass, form, group_sources())
    repository = get_group_repository(hass)
    with patch.object(type(repository.store), "async_save", side_effect=OSError("disk full")):
        result = await submit(hass, form, policy())
    assert result["errors"]["base"] == "group_storage_error"
    assert repository.registry.groups == ()
    assert repository.registry.memberships == ()


async def test_group_join_priority_leave_and_delete(hass):
    first, second, repository, group_id = await setup_shadow_group(hass)
    await repository.async_update(lambda state: state.leave(second.runtime_data.device_id))
    form = await group_form(hass, second, "group_join")
    result = await submit(hass, form, {"group_id": group_id, "priority": 20})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert repository.registry.membership(second.runtime_data.device_id).priority == 20
    form = await group_form(hass, second, "group_member")
    result = await submit(hass, form, {"name": "Shared roof", "priority": 30})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert repository.registry.group(group_id).name == "Shared roof"
    assert first.runtime_data.data["group_name"] == "Shared roof"
    for entry in (first, second):
        form = await group_form(hass, entry, "group_leave")
        assert (await submit(hass, form, {}))["type"] == "create_entry"
        await hass.async_block_till_done()
        assert entry.runtime_data.data["group_action"] == "independent"
    form = await group_form(hass, first, "group_delete")
    assert (await submit(hass, form, {"group_id": group_id}))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert repository.registry.groups == ()


async def test_group_edit_detects_stale_form_and_preserves_reservations(hass):
    first, _, repository, group_id = await setup_shadow_group(hass)
    form = await group_form(hass, first, "group_policy")
    original = repository.registry.group(group_id)
    await repository.async_update(
        lambda state: state.update(replace(original, name="Changed elsewhere"))
    )
    result = await submit(hass, form, policy())
    assert result["errors"]["base"] == "configuration_changed"
    await repository.async_update(
        lambda state: replace(
            state, unresolved=(UnresolvedReservation(first.runtime_data.device_id, group_id, 900),)
        )
    )
    before = repository.registry
    form = await group_form(hass, first, "group_leave")
    result = await submit(hass, form, {})
    assert result["errors"]["base"] == "unresolved_reservation"
    assert repository.registry is before


async def test_group_join_does_not_switch_active_control_implicitly(hass):
    first, second, repository, group_id = await setup_shadow_group(hass)
    await repository.async_update(lambda state: state.leave(second.runtime_data.device_id))
    first.runtime_data._set_operation_mode("control")
    form = await group_form(hass, second, "group_join")
    result = await submit(hass, form, {"group_id": group_id, "priority": 0})
    assert result["errors"]["base"] in ("switch_to_observation", "unresolved_reservation")
    assert repository.registry.membership(second.runtime_data.device_id) is None
    assert first.runtime_data.settings["operation_mode"] == "control"


async def test_group_member_local_forms_do_not_edit_shared_policy(hass):
    first, _, repository, group_id = await setup_shadow_group(hass)
    form = await options(hass, first, "sources")
    assert {str(k) for k in form["data_schema"].schema} == {
        "comfort", "consumption", "settings_action",
    }
    form = await options(hass, first, "energy")
    assert {str(k) for k in form["data_schema"].schema} == {
        "comfort", "consumption", "settings_action",
    }
    before = repository.registry.group(group_id)
    result = await submit(hass, form, {"estimated_ac_power": 1200})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert repository.registry.group(group_id) == before
    assert first.runtime_data.settings["estimated_ac_power"] == 1200


@pytest.mark.parametrize("mode", ["observation", "disabled", "temporary_block"])
async def test_reconfigure_preserves_device_entities_group_and_mode(hass, mode):
    first, _, repository, group_id = await setup_shadow_group(hass)
    await first.runtime_data.async_set_mode(mode)
    identity = first.runtime_data.device_id
    before_options = dict(first.options)
    registry = er.async_get(hass)
    old_sensor = registry.async_get_entity_id("sensor", DOMAIN, f"{first.entry_id}_temperature")
    hass.states.async_set(
        "climate.replacement",
        "off",
        {"hvac_modes": ["heat", "cool", "off"], "current_temperature": 21},
    )
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": first.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {"climate_entity": "climate.replacement", "temperature_entity": "sensor.room"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert first.runtime_data.device_id == identity
    assert first.runtime_data.settings["operation_mode"] == mode
    assert repository.registry.membership(identity).group_id == group_id
    assert first.unique_id == "climate.replacement"
    assert (
        registry.async_get_entity_id("sensor", DOMAIN, f"{first.entry_id}_temperature")
        == old_sensor
    )
    for key in ("temporary_block_date", "temporary_previous_mode"):
        assert first.options.get(key) == before_options.get(key)


async def test_reconfigure_rejects_duplicate_and_pending_reserve(hass):
    first, _, repository, group_id = await setup_shadow_group(hass)
    original = dict(first.data)
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": first.entry_id}
    )
    form = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"climate_entity": "climate.second", "temperature_entity": "sensor.room"}
    )
    assert form["errors"]["base"] == "already_configured"
    await repository.async_update(
        lambda state: replace(
            state, unresolved=(UnresolvedReservation(first.runtime_data.device_id, group_id, 900),)
        )
    )
    form = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"climate_entity": "climate.test", "temperature_entity": "sensor.room"}
    )
    assert form["errors"]["base"] == "unresolved_reservation"
    assert dict(first.data) == original


async def test_group_sensors_distinguish_proposals_and_actual_reservations(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    await hass.async_block_till_done()
    data = first.runtime_data.data
    assert data["group_available_power"] == 1000
    assert data["group_reserved_power"] == 0
    assert data["group_load_power"] == 600
    assert data["group_action"].startswith("preview_")
    registry = er.async_get(hass)
    sensor = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{first.entry_id}_group_reserved_power"
    )
    assert float(hass.states.get(sensor).state) == 0
    with patch.object(type(hass.services), "async_call"):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert first.runtime_data.data["group_reserved_power"] == 900
        assert first.runtime_data.data["group_available_power"] == 100
        assert float(hass.states.get(sensor).state) == 900
        owner = next(
            e
            for e in (first, second)
            if e.runtime_data.device_id == repository.registry.unresolved[0].device_id
        )
        assert owner.runtime_data.data["group_command_status"] == "awaiting_confirmation"
        hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
        await hass.async_block_till_done()
        assert owner.runtime_data.data["group_action"] == "stop"
        assert owner.runtime_data.data["group_command_status"] == "awaiting_stop"


async def test_mode_change_during_group_save_cannot_bypass_authority(hass):
    import asyncio

    first, second, repository, group_id = await setup_shadow_group(hass)
    second_id = second.runtime_data.device_id
    await repository.async_update(lambda state: state.leave(second_id))
    # Its local policy would otherwise allow an immediate standalone start.
    second.runtime_data.settings.update(
        soc_entity="sensor.soc",
        battery_power_entity="sensor.battery",
        grid_available_entity="binary_sensor.grid",
    )
    hass.states.async_set("binary_sensor.grid", "on")
    form = await group_form(hass, second, "group_join")
    entered, release = asyncio.Event(), asyncio.Event()
    save = repository.store.async_save

    async def delayed(data):
        entered.set()
        await release.wait()
        await save(data)

    with (
        patch.object(type(repository.store), "async_save", side_effect=delayed),
        patch.object(type(hass.services), "async_call") as calls,
    ):
        task = asyncio.create_task(submit(hass, form, {"group_id": group_id, "priority": 0}))
        try:
            await asyncio.wait_for(entered.wait(), 5)
            second.runtime_data._set_operation_mode("control")
            second.runtime_data._evaluate()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            calls.assert_not_called()
            assert second_id in second.runtime_data.group_manager.mutating_devices
        finally:
            release.set()
            result = await task
        assert result["type"] == "create_entry"
        await hass.async_block_till_done()
        assert second_id not in second.runtime_data.group_manager.mutating_devices
        # If a start occurs after saving, it must carry a durable group reservation.
        if any(c.args[1] == "set_temperature" for c in calls.call_args_list):
            assert any(r.device_id == second_id for r in repository.registry.unresolved)


async def test_group_sources_update_and_clear_optional_source(hass):
    first, second, repository, group_id = await setup_shadow_group(hass)
    form = await group_form(hass, first, "group_sources")
    values = group_sources()
    values.pop("pv_power_entity")
    result = await submit(hass, form, values)
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert repository.registry.group(group_id).sources.pv_power_entity is None
    assert first.runtime_data.data["group_reason"] == "invalid_solar_data"
    assert second.runtime_data.data["group_reason"] == "invalid_solar_data"


async def test_entry_removal_detaches_only_resolved_member(hass):
    from custom_components.solar_climate_manager import async_remove_entry

    first, second, repository, group_id = await setup_shadow_group(hass)
    second_id = second.runtime_data.device_id
    first_id = first.runtime_data.device_id
    await repository.async_update(
        lambda state: replace(state, unresolved=(UnresolvedReservation(first_id, group_id, 900),))
    )
    assert await hass.config_entries.async_remove(second.entry_id)
    assert repository.registry.membership(second_id) is None
    await async_remove_entry(hass, first)
    assert repository.registry.membership(first_id) is not None
    assert repository.registry.unresolved


async def test_group_diagnostics_redact_name_and_sources(hass):
    from custom_components.solar_climate_manager.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    first, _, repository, group_id = await setup_shadow_group(hass)
    await repository.async_update(
        lambda state: state.update(replace(state.group(group_id), name="Private personal house"))
    )
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, first)
    assert "Private personal house" not in str(diagnostics)
    assert "sensor.pv" not in str(diagnostics)
    assert diagnostics["decision"]["group_reserved_power"] == 0


async def test_missing_meter_can_be_added_without_erasing_pending_reserve(hass):
    first, _, repository, group_id = await setup_shadow_group(hass)
    identity = first.runtime_data.device_id
    await repository.async_update(
        lambda state: replace(state, unresolved=(UnresolvedReservation(identity, group_id, 900),))
    )
    reserve = repository.registry.unresolved[0]
    hass.states.async_set("sensor.ac_new", "0", {"unit_of_measurement": "W"})
    form = await options(hass, first, "sources")
    result = await submit(hass, form, {"ac_power_entity": "sensor.ac_new"})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert first.runtime_data.settings["ac_power_entity"] == "sensor.ac_new"
    assert repository.registry.unresolved == (reserve,)
    hass.states.async_set("sensor.ac_different", "0", {"unit_of_measurement": "W"})
    form = await options(hass, first, "sources")
    result = await submit(hass, form, {"ac_power_entity": "sensor.ac_different"})
    assert result["errors"]["base"] == "unresolved_reservation"
    assert repository.registry.unresolved == (reserve,)


async def test_reconfigure_can_change_supported_hvac_mode(hass):
    first = await setup(hass)
    hass.states.async_set(
        "climate.cool_only", "off", {"hvac_modes": ["cool", "off"], "current_temperature": 26}
    )
    form = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": first.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            "climate_entity": "climate.cool_only",
            "temperature_entity": "sensor.room",
            "hvac_mode": "cool",
        },
    )
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert first.runtime_data.settings["hvac_mode"] == "cool"
    assert first.runtime_data.settings["operation_mode"] == "observation"


@pytest.mark.parametrize("name", ["   ", "x" * 256])
async def test_group_wizard_rejects_name_outside_ha_state_limit(hass, name):
    entry = await setup(hass)
    form = await group_form(hass, entry, "group_create")
    result = await submit(hass, form, {"name": name, "priority": 0})
    assert result["errors"]["base"] == "invalid_identifier"
    assert get_group_repository(hass).registry.groups == ()
