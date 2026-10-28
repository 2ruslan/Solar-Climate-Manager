"""Live group forecast updates permit low-SOC starts and revoke lost coverage."""

from unittest.mock import patch

from test_integration import attach_energy_group, setup


async def test_forecast_allows_low_soc_start_and_updates_live(hass):
    entry = await setup(hass)
    for entity, value, unit in (
        ("sensor.soc", "20", "%"), ("sensor.battery", "0", "W"),
        ("sensor.pv", "100", "W"), ("sensor.forecast", "2", "kW"),
    ):
        hass.states.async_set(entity, value, {"unit_of_measurement": unit})
    hass.states.async_set("binary_sensor.grid", "off")
    await attach_energy_group(hass, entry, pv_power_entity="sensor.pv",
                              generation_forecast_entity="sensor.forecast")
    coordinator = entry.runtime_data
    assert coordinator.data["energy_allowed"]
    assert coordinator.data["strategy_action"] == "start"
    assert coordinator.data["group_action"] == "preview_start"
    hass.states.async_set("sensor.forecast", "0.5", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert not coordinator.data["energy_allowed"]
    assert coordinator.data["group_action"] == "preview_wait"
    hass.states.async_set("sensor.forecast", "2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert coordinator.data["energy_allowed"]
    assert coordinator.data["group_action"] == "preview_start"
    with patch.object(type(hass.services), "async_call") as calls:
        await coordinator.async_set_mode("control")
        await hass.async_block_till_done()
        assert any(call.args[1] == "set_temperature" for call in calls.call_args_list)
        calls.reset_mock()
        hass.states.async_set("sensor.forecast", "0.5", {"unit_of_measurement": "kW"})
        await hass.async_block_till_done()
        assert any(call.args[1] == "set_hvac_mode" and call.args[2]["hvac_mode"] == "off"
                   for call in calls.call_args_list)
    assert await hass.config_entries.async_unload(entry.entry_id)
