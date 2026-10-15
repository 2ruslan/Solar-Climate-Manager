"""Exercise flow, platform setup, observation safety and persistence in HA."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.solar_climate_manager.const import DEFAULTS, DOMAIN


def inputs():
    return {**DEFAULTS, "climate_entity": "climate.test", "temperature_entity": "sensor.room"}


def basic_inputs():
    return {
        key: value
        for key, value in inputs().items()
        if key
        in {"climate_entity", "temperature_entity", "target_temperature", "hysteresis", "hvac_mode"}
    }


def states(hass, temperature="21"):
    hass.states.async_set(
        "climate.test", "off", {"hvac_modes": ["off", "heat", "cool"], "current_temperature": 21}
    )
    hass.states.async_set(
        "sensor.room", temperature, {"device_class": "temperature", "unit_of_measurement": "°C"}
    )


async def setup(hass, *, energy_ready=False):
    states(hass)
    data = inputs()
    if energy_ready:
        hass.states.async_set("sensor.soc", "95", {"unit_of_measurement": "%"})
        hass.states.async_set("sensor.battery", "0", {"unit_of_measurement": "W"})
        hass.states.async_set("binary_sensor.grid", "on")
        data.update(
            soc_entity="sensor.soc",
            battery_power_entity="sensor.battery",
            grid_available_entity="binary_sensor.grid",
        )
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="climate.test")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_flow_and_duplicate(hass):
    states(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], basic_inputs())
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=inputs()
    )
    assert duplicate["reason"] == "already_configured"


async def test_flow_rejects_unsupported_mode(hass):
    states(hass)
    hass.states.async_set("climate.test", "off", {"hvac_modes": ["off", "cool"]})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=inputs()
    )
    assert result["errors"]["base"] == "unsupported_mode"


async def test_observation_and_unavailable_data(hass):
    with patch.object(type(hass.services), "async_call") as calls:
        entry = await setup(hass)
        coordinator = entry.runtime_data
        assert coordinator.data["demand"]
        assert coordinator.data["control_allowed"] is False
        hass.states.async_set("sensor.room", "23", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done()
        assert coordinator.data["demand"]
        hass.states.async_set("sensor.room", "unavailable")
        await hass.async_block_till_done()
        assert coordinator.data["invalid_data"]
        assert not coordinator.data["demand"]
        calls.assert_not_called()


async def test_reload_restores_hysteresis_and_options_reset(hass):
    entry = await setup(hass)
    hass.states.async_set("sensor.room", "23", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["demand"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "comfort"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "target_temperature": 20,
            "temperature_entity": "sensor.room",
            "hysteresis": 1,
            "hvac_mode": "heat",
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert not entry.runtime_data.data["demand"]


async def test_unchanged_temperature_does_not_expire(hass):
    entry = await setup(hass)
    with patch(
        "custom_components.solar_climate_manager.coordinator.dt_util.utcnow",
        return_value=dt_util.utcnow() + timedelta(days=2),
    ):
        entry.runtime_data._evaluate()
    assert not entry.runtime_data.data["invalid_data"]
    assert entry.runtime_data.data["temperature"] == 21
    assert entry.runtime_data.data["demand"]


async def test_disabled_persists(hass):
    entry = await setup(hass)
    hass.config_entries.async_update_entry(entry, options={"operation_mode": "disabled"})
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["automation_mode"] == "disabled"
    assert not entry.runtime_data.data["demand"]


async def test_solar_sources_independent_of_temperature(hass):
    states(hass)
    hass.states.async_set("sensor.pv", "2.8", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(domain=DOMAIN, data={**inputs(), "pv_power_entity": "sensor.pv"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["pv_power"] == 2800
    assert entry.runtime_data.data["forecast_power_now"] is None
    hass.states.async_set("sensor.pv", "unavailable")
    await hass.async_block_till_done()
    assert entry.runtime_data.data["pv_power"] is None
    assert entry.runtime_data.data["demand"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sources"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "load_includes_ac": True,
            "load_includes_battery_charging": False,
            "grid_on_means_available": True,
            "battery_positive": "discharge",
            "grid_positive": "import",
        },
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["pv_power_entity"] is None
    assert entry.runtime_data.settings["pv_power_entity"] is None


async def test_reject_energy_sensor_as_forecast(hass):
    states(hass)
    hass.states.async_set("sensor.energy", "5", {"unit_of_measurement": "kWh"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={**inputs(), "forecast_power_now_entity": "sensor.energy"},
    )
    assert result["errors"]["base"] == "invalid_power"


async def test_select_mode_replaces_switch_and_survives_reload(hass):
    entry = await setup(hass)
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_operation_mode")
    assert entity_id is not None
    assert registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_enabled") is None
    assert hass.states.get(entity_id).attributes["options"] == [
        "disabled",
        "observation",
        "control",
        "temporary_block",
    ]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "disabled"}, blocking=True
    )
    assert entry.options["operation_mode"] == "disabled"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "disabled"


async def test_grid_energy_permission_survives_disabled_mode(hass):
    states(hass)
    hass.states.async_set("binary_sensor.grid", "on")
    hass.states.async_set("sensor.soc", "95", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.battery", "0", {"unit_of_measurement": "W"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **inputs(),
            "operation_mode": "disabled",
            "grid_available_entity": "binary_sensor.grid",
            "soc_entity": "sensor.soc",
            "battery_power_entity": "sensor.battery",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["energy_allowed"]
    assert entry.runtime_data.data["energy_reason"] == "grid_ready"
    assert not entry.runtime_data.data["control_allowed"]
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for key, expected in (("energy_reason", "grid_ready"), ("command_error", "none")):
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
        assert hass.states.get(entity_id).state == expected
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(("maximum", "expected_target"), [(27, 27), (35, 30)])
async def test_ac_temperature_and_compensated_target_sensors(hass, maximum, expected_target):
    from homeassistant.helpers import entity_registry as er

    states(hass)
    hass.states.async_set(
        "climate.test",
        "off",
        {
            "hvac_modes": ["off", "heat", "cool"],
            "current_temperature": 28,
            "temperature": 29,
            "min_temp": 16,
            "max_temp": 30,
            "target_temp_step": 1,
        },
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**inputs(), "ac_max_temperature": maximum},
        unique_id="climate.test",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for key, expected in (
        ("ac_temperature", 28),
        ("temperature_offset", 7),
        ("ac_target_temperature", expected_target),
        ("ac_set_temperature", 29),
    ):
        entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
        assert float(hass.states.get(entity_id).state) == expected
    decision_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_strategy_action"
    )
    assert hass.states.get(decision_id).attributes["ac_target_temperature_c"] == expected_target
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_inverter_limit_and_low_soc_charging(hass):
    states(hass)
    hass.states.async_set("binary_sensor.grid", "on")
    hass.states.async_set("sensor.soc", "60", {"unit_of_measurement": "%"})
    hass.states.async_set("sensor.battery", "-1200", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.grid", "2000", {"unit_of_measurement": "W"})
    hass.states.async_set("number.limit", "3", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            **inputs(),
            "grid_available_entity": "binary_sensor.grid",
            "soc_entity": "sensor.soc",
            "battery_power_entity": "sensor.battery",
            "grid_power_entity": "sensor.grid",
            "grid_import_limit_entity": "number.limit",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["energy_allowed"]
    assert entry.runtime_data.data["grid_import_limit"] == 3000
    assert entry.runtime_data.data["grid_import_margin"] == 100
    hass.states.async_set("number.limit", "2", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert entry.runtime_data.data["energy_reason"] == "grid_import_limit"
    assert not entry.runtime_data.data["energy_allowed"]
    hass.states.async_set("number.limit", "0", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert entry.runtime_data.data["energy_allowed"]
    assert not entry.runtime_data.data["grid_import_limit_active"]
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("mode", ["disabled", "observation", "temporary_block"])
async def test_non_control_modes_send_no_climate_commands(hass, mode):
    entry = await setup(hass, energy_ready=True)
    assert entry.runtime_data.data["strategy_action"] == "start"
    with patch.object(type(hass.services), "async_call") as calls:
        await entry.runtime_data.async_set_mode(mode)
        hass.states.async_set("sensor.room", "18", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done()
        assert entry.runtime_data.data["control_allowed"] is False
        calls.assert_not_called()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_temporary_block_survives_reload_and_returns_at_local_midnight(hass, freezer):
    await hass.config.async_set_time_zone("Europe/Kyiv")
    # Midnight in Kyiv is still the previous UTC date.
    freezer.move_to("2026-10-14T20:59:40+00:00")
    entry = await setup(hass)
    await entry.runtime_data.async_set_mode("temporary_block")
    assert entry.options["temporary_previous_mode"] == "observation"
    assert entry.options["temporary_block_date"] == "2026-10-14"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["automation_mode"] == "temporary_block"
    freezer.move_to("2026-10-14T21:00:15+00:00")
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert entry.runtime_data.data["automation_mode"] == "observation"
    assert "temporary_block_date" not in entry.options
    assert "temporary_previous_mode" not in entry.options
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unload_cancels_inflight_climate_command(hass):
    entry = await setup(hass, energy_ready=True)
    coordinator = entry.runtime_data
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def pending_command(domain, service, data, **kwargs):
        assert domain == "climate"
        assert service == "set_temperature"
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with patch.object(type(hass.services), "async_call", side_effect=pending_command):
        await coordinator.async_set_mode("control")
        await asyncio.wait_for(started.wait(), timeout=2)
        task = coordinator.command_task
        assert task is not None
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert cancelled.is_set()
        assert task.done()
        assert coordinator.command_task is None
        assert coordinator.closed
