"""Group estimation through real HA forms, state reports and reload."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from test_group_ui import options, submit
from test_integration import enable_group_control, setup_shadow_group


async def configure(hass, entry, **updates):
    form = await options(hass, entry, "energy")
    return await submit(hass, form, {
        "estimated_ac_power": 900, "power_accounting": "estimated",
        "power_settle_seconds": 30, **updates,
    })


async def prepare(hass, scope="includes_all_members", mixed=False):
    first, second, repository, group_id = await setup_shadow_group(hass)
    for entry in (first, second):
        assert (await configure(hass, entry))["type"] == "create_entry"
        await hass.async_block_till_done()
    if mixed:
        hass.states.async_set("sensor.ac_two", "0", {"unit_of_measurement": "W"})
        assert (await configure(hass, second, power_accounting="meter", ac_power_entity="sensor.ac_two"))["type"] == "create_entry"
        await hass.async_block_till_done()
    await repository.async_update(lambda state: replace(
        state.update(replace(state.group(group_id), policy=replace(state.group(group_id).policy, load_scope=scope))),
        memberships=tuple(replace(m, priority=10) if m.device_id == first.runtime_data.device_id else m for m in state.memberships),
    ))
    hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    return first, second, repository, group_id


def report(hass, record, state="heat"):
    _, data, context = record
    hass.states.async_set(data["entity_id"], state, {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21,
        "temperature": data.get("temperature", 25),
    }, context=context, force_update=True)


@pytest.mark.parametrize("scope,mixed", [
    ("includes_all_members", False), ("excludes_all_members", False),
    ("includes_all_members", True), ("excludes_all_members", True),
])
async def test_estimated_sequential_starts_wait_for_settled_reports(hass, freezer, scope, mixed):
    first, second, repository, group_id = await prepare(hass, scope, mixed)
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert len(records) == 1
        assert repository.registry.unresolved[0].watts == 900
        freezer.tick(timedelta(seconds=1))
        report(hass, records[0])
        await hass.async_block_till_done()
        assert first.runtime_data.commands.state.attempt.confirmed_at is not None
        assert first.runtime_data.data["group_command_status"] == "awaiting_stabilization"
        freezer.tick(timedelta(seconds=10))
        hass.states.async_set("sensor.load", "800", {"unit_of_measurement": "W"}, force_update=True)
        await hass.async_block_till_done()
        assert len(records) == 1
        freezer.tick(timedelta(seconds=30))
        first.runtime_data.group_manager.request_evaluation()
        await hass.async_block_till_done()
        assert len(records) == 1  # elapsed time without a new report proves nothing
        hass.states.async_set("sensor.load", "800", {"unit_of_measurement": "W"}, force_update=True)
        await hass.async_block_till_done()
        assert len(records) == 2
        assert records[1][1]["entity_id"] == "climate.second"
        assert len(repository.registry.unresolved) == 1
        assert repository.registry.unresolved[0].device_id == second.runtime_data.device_id
        snapshot = first.runtime_data.group_manager.snapshots[group_id]
        assert snapshot.requests[0].measured_watts is None
        assert first.runtime_data.data["group_load_power"] == (800 if scope == "includes_all_members" else 1700)


async def test_group_keeps_running_with_last_temperature_until_sensor_recovers(hass, freezer):
    first, second, _, group_id = await prepare(hass)
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first)
        await hass.async_block_till_done()
        freezer.tick(timedelta(seconds=1))
        report(hass, records[0])
        await hass.async_block_till_done()
        previous_temperature = first.runtime_data.data["temperature"]
        entity = first.runtime_data.settings["temperature_entity"]
        hass.states.async_set(entity, "unavailable")
        await hass.async_block_till_done()
        assert first.runtime_data.data["temperature"] == previous_temperature
        snapshot = first.runtime_data.group_manager.snapshots[group_id]
        request = next(r for r in snapshot.requests if r.device_id == first.runtime_data.device_id)
        assert request.temperature_valid
        assert request.demand
        assert request.running
        assert all(name != "set_hvac_mode" for name, _, _ in records)
        hass.states.async_set(entity, "30", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done()
        assert first.runtime_data.data["temperature"] == 30
        assert not first.runtime_data.data["demand"]


async def test_estimated_form_validation_and_live_or_pending_changes_blocked(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    assert first.runtime_data.settings["power_accounting"] == "legacy"
    result = await configure(hass, first, power_accounting="meter")
    assert result["errors"]["base"] == "missing_power_meter"
    assert first.runtime_data.settings["power_accounting"] == "legacy"
    assert (await configure(hass, first))["type"] == "create_entry"
    await hass.async_block_till_done()
    with patch.object(type(hass.services), "async_call"):
        hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
        enable_group_control(first)
        await hass.async_block_till_done()
        assert repository.registry.unresolved
        # Pending reservation has priority over mode checks, and is never erased.
        result = await configure(hass, first, estimated_ac_power=1100)
        assert result["errors"]["base"] == "unresolved_reservation"
        first.runtime_data._set_operation_mode("observation")
        await hass.async_block_till_done()
        result = await configure(hass, first, power_accounting="legacy")
        assert result["errors"]["base"] == "unresolved_reservation"
        second.runtime_data._set_operation_mode("control")
        result = await configure(hass, second)
        assert result["errors"]["base"] == "switch_to_observation"


@pytest.mark.parametrize("accounting", ["estimated", "legacy"])
async def test_estimated_reload_recovers_via_off_then_new_aggregate(hass, freezer, accounting):
    first, second, repository, _ = await prepare(hass)
    assert (await configure(hass, first, power_accounting=accounting,
                            power_settle_seconds=120))["type"] == "create_entry"
    await hass.async_block_till_done()
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        freezer.tick(timedelta(seconds=1))
        report(hass, records[0])
        await hass.async_block_till_done()
        token = repository.registry.unresolved[0].command_id
        assert await hass.config_entries.async_reload(first.entry_id)
        await hass.async_block_till_done()
        assert [r[0] for r in records] == ["set_temperature", "set_hvac_mode"]
        assert repository.registry.unresolved[0].command_id == token
        assert first.runtime_data.data["effective_power_accounting"] == "estimated"
        assert first.runtime_data.group_manager.desired(first.runtime_data.device_id) is False
        freezer.tick(timedelta(seconds=1))
        report(hass, records[-1], "off")
        await hass.async_block_till_done()
        freezer.tick(timedelta(seconds=31))
        first.runtime_data.group_manager.request_evaluation()
        await hass.async_block_till_done()
        assert len(records) == 2  # Do not restart a 120-second wait every 30 seconds.
        freezer.tick(timedelta(seconds=90))
        hass.states.async_set("sensor.load", "600", {"unit_of_measurement": "W"}, force_update=True)
        await hass.async_block_till_done()
        assert records[-1][0] == "set_temperature"
        assert records[-1][1]["entity_id"] == "climate.second"
        assert all(r.command_id != token for r in repository.registry.unresolved)


async def test_failed_estimated_start_is_not_released_by_running_report(hass, freezer):
    first, second, repository, _ = await prepare(hass)
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))
        if name == "set_temperature":
            raise HomeAssistantError("transport failed")

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert repository.registry.unresolved[0].phase == "uncertain"
        freezer.tick(timedelta(seconds=40))
        report(hass, records[0])
        hass.states.async_set("sensor.load", "800", {"unit_of_measurement": "W"}, force_update=True)
        await hass.async_block_till_done()
        assert repository.registry.unresolved
        assert sum(r[0] == "set_temperature" for r in records) == 1


async def test_pending_service_cannot_settle_estimated_start(hass, freezer):
    first, second, repository, _ = await prepare(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    evaluated = asyncio.Event()
    manager = first.runtime_data.group_manager
    settle = manager._settle

    async def checked(group):
        await settle(group)
        evaluated.set()

    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))
        if len(records) == 1:
            entered.set()
            await release.wait()

    with patch.object(type(hass.services), "async_call", side_effect=service):
        try:
            enable_group_control(first, second)
            await asyncio.wait_for(entered.wait(), 5)
            freezer.tick(timedelta(seconds=1))
            report(hass, records[0])
            # Drain group evaluation only; the deliberately blocked service is
            # itself a tracked HA task and cannot be awaited until release.
            with patch.object(manager, "_settle", side_effect=checked):
                manager.request_evaluation()
                await asyncio.wait_for(evaluated.wait(), 5)
            freezer.tick(timedelta(seconds=31))
            evaluated.clear()
            with patch.object(manager, "_settle", side_effect=checked):
                hass.states.async_set("sensor.load", "800", {"unit_of_measurement": "W"}, force_update=True)
                manager.request_evaluation()
                await asyncio.wait_for(evaluated.wait(), 5)
            assert len(records) == 1
            assert repository.registry.unresolved
        finally:
            release.set()
            await hass.async_block_till_done()
        assert len(records) == 2
