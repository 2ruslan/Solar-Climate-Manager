"""Passive analysis observes actual states, persists, and never dispatches commands."""

from dataclasses import replace
from unittest.mock import patch

from test_integration import attach_energy_group, setup

from custom_components.solar_climate_manager.panel import async_overview
from custom_components.solar_climate_manager.runtime.power_analysis import PowerAnalysis


async def install(hass):
    entry = await setup(hass)
    hass.states.async_set("climate.test", "off", {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21,
        "temperature": 24, "fan_mode": "auto"})
    await attach_energy_group(hass, entry)
    return entry


async def test_passive_analysis_collects_off_background_and_persists_cycle(hass, freezer):
    entry = await install(hass)
    coordinator = entry.runtime_data
    manager = coordinator.group_manager
    group_id = manager.repository.registry.groups[0].group_id
    climate_attrs = dict(hass.states.get("climate.test").attributes)

    async def report(watts):
        freezer.tick(30)
        hass.states.async_set("sensor.load", str(watts), {"unit_of_measurement": "W"}, force_update=True)
        await hass.async_block_till_done()

    with patch.object(type(hass.services), "async_call") as calls:
        for _ in range(5):
            await report(600)
        assert manager.power_analysis.background_view(group_id)["watts"] == 600
        hass.states.async_set("climate.test", "heat", climate_attrs)
        for _ in range(36):
            await report(1200)
        assert manager.power_analysis.groups[group_id].pending
        live = manager.power_analysis.view(group_id, coordinator)["adaptive"]
        assert live["windows"] >= 1
        assert live["low"] < 600 < live["high"]
        hass.states.async_set("climate.test", "off", climate_attrs)
        for _ in range(5):
            await report(600)
        view = manager.power_analysis.view(group_id, coordinator)
        assert view["cycles"] == 1
        assert view["watts"] is None
        assert {row["watts"] for row in view["profiles"]} == {600}
        assert view["analysis_only"]
        data = await async_overview(hass)
        assert data["devices"][0]["power_analysis"]["cycles"] == 1
        assert data["groups"][0]["background_analysis"]["samples"] >= 8
        await manager.power_analysis.async_flush()
        restored = PowerAnalysis(hass)
        await restored.async_load()
        assert restored.view(group_id, coordinator)["cycles"] == 1
        assert restored.view(group_id, coordinator)["adaptive"]["profiles"]
        assert restored.groups[group_id].active is None
        calls.assert_not_called()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_analysis_context_tracks_sources_but_not_targets(hass, freezer):
    entry = await install(hass)
    manager = entry.runtime_data.group_manager
    repository = manager.repository
    group = repository.registry.groups[0]
    for _ in range(3):
        freezer.tick(30)
        hass.states.async_set("sensor.load", "600", {"unit_of_measurement": "W"}, force_update=True)
        await hass.async_block_till_done()
    original = manager.power_analysis.groups[group.group_id]
    entry.runtime_data.settings["target_temperature"] = 26
    entry.runtime_data._evaluate()
    await hass.async_block_till_done()
    assert manager.power_analysis.groups[group.group_id] is original
    await repository.async_update(lambda state: state.update(replace(
        group, policy=replace(group.policy, load_scope="excludes_all_members"))))
    await hass.async_block_till_done()
    model = manager.power_analysis.groups[group.group_id]
    assert model is not original
    assert model.status == "unsupported_load"
    assert not model.background
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_analysis_storage_failure_does_not_block_existing_control(hass):
    entry = await setup(hass, energy_ready=True)
    manager = entry.runtime_data.group_manager
    manager.power_analysis.error = "storage_error"
    with patch.object(type(hass.services), "async_call") as calls:
        await entry.runtime_data.async_set_mode("control")
        await hass.async_block_till_done()
        assert any(c.args[1] == "set_temperature" for c in calls.call_args_list)
    assert manager.error is None
    assert await hass.config_entries.async_unload(entry.entry_id)
