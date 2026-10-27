"""Group settings are the sole source for readings, history and device diagnostics."""

from dataclasses import replace
from unittest.mock import patch

from test_integration import setup, setup_shadow_group

from custom_components.solar_climate_manager.domain.configuration import GROUP_SETTING_KEYS
from custom_components.solar_climate_manager.domain.groups import GroupPolicy, GroupSources


async def test_device_without_group_never_uses_legacy_energy_or_sends_commands(hass):
    entry = await setup(hass)
    hass.states.async_set("sensor.old", "9000", {"unit_of_measurement": "W"})
    hass.config_entries.async_update_entry(entry, options={
        "operation_mode": "control", "pv_power_entity": "sensor.old",
        "generation_forecast_entity": "sensor.old", "minimum_soc": 1,
    })
    with patch.object(type(hass.services), "async_call") as calls:
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        data = entry.runtime_data.data
        assert data["group_reason"] == "not_grouped"
        assert data["control_allowed"] is False
        assert data["generation_forecast"] is None
        assert not GROUP_SETTING_KEYS.intersection(entry.data)
        assert not GROUP_SETTING_KEYS.intersection(entry.options)
        calls.assert_not_called()


async def test_shared_settings_read_live_without_copy_and_follow_membership(hass):
    first, second, repository, group_id = await setup_shadow_group(hass)
    original = repository.registry.group(group_id)
    hass.states.async_set("sensor.forecast_shared", "2.5", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.old", "9999", {"unit_of_measurement": "W"})
    group = replace(original, sources=replace(original.sources,
                    generation_forecast_entity="sensor.forecast_shared"),
                    policy=replace(original.policy, minimum_soc=70, restart_soc=80))
    await repository.async_update(lambda state: state.update(group))
    hass.config_entries.async_update_entry(first, options={
        **first.options, "generation_forecast_entity": "sensor.old", "minimum_soc": 1,
        "load_power_entity": "sensor.old",
    })
    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()
    for entry in (first, second):
        coordinator = entry.runtime_data
        assert coordinator.data["generation_forecast"] == 2500
        assert coordinator.data["load_power"] == 600
        assert coordinator.history.latest["state"]["generation_forecast"] == 2500
        assert coordinator.effective_settings()["minimum_soc"] == 70
        for values in (entry.data, entry.options, coordinator.settings):
            assert not GROUP_SETTING_KEYS.intersection(values)
    assert repository.registry.group(group_id) == group
    await repository.async_update(lambda state: state.update(replace(group,
        sources=replace(group.sources, generation_forecast_entity=None),
        policy=replace(group.policy, minimum_soc=60))))
    await hass.async_block_till_done()
    assert first.runtime_data.data["generation_forecast"] is None
    assert first.runtime_data.effective_settings()["minimum_soc"] == 60
    await repository.async_update(lambda state: state.leave(first.runtime_data.device_id))
    await hass.async_block_till_done()
    assert first.runtime_data.data["group_reason"] == "not_grouped"
    assert first.runtime_data.data["load_power"] is None
    registry = await repository.async_update(lambda state: state.create(
        "Other", GroupSources(load_power_entity="sensor.old", soc_entity="sensor.soc",
                              battery_power_entity="sensor.battery",
                              grid_available_entity="binary_sensor.grid"), GroupPolicy())[0])
    await repository.async_update(lambda state: state.join(first.runtime_data.device_id,
                                                          registry.groups[-1].group_id))
    await hass.async_block_till_done()
    assert first.runtime_data.data["load_power"] == 9999
    assert second.runtime_data.data["load_power"] == 600
