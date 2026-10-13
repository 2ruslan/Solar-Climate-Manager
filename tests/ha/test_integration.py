"""Exercise flow, platform setup, observation safety and persistence in HA."""

from datetime import timedelta
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    hass.states.async_set("climate.test", "off", {"hvac_modes": ["off", "heat", "cool"]})
    hass.states.async_set(
        "sensor.room", temperature, {"device_class": "temperature", "unit_of_measurement": "°C"}
    )


async def setup(hass):
    states(hass)
    entry = MockConfigEntry(domain=DOMAIN, data=inputs(), unique_id="climate.test")
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
    with patch.object(hass.services, "async_call") as calls:
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


async def test_stale_reading(hass):
    entry = await setup(hass)
    with patch(
        "custom_components.solar_climate_manager.coordinator.dt_util.utcnow",
        return_value=dt_util.utcnow() + timedelta(seconds=901),
    ):
        entry.runtime_data._evaluate()
    assert entry.runtime_data.data["invalid_data"]


async def test_disabled_persists(hass):
    entry = await setup(hass)
    hass.config_entries.async_update_entry(entry, options={"enabled": False})
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
