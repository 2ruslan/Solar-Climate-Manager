"""Exercise flow, platform setup, observation safety and persistence in HA."""

import asyncio
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.solar_climate_manager.const import DEFAULTS, DOMAIN
from custom_components.solar_climate_manager.flow_helpers import SETTINGS_SECTIONS
from custom_components.solar_climate_manager.settings import (
    ACCOUNTING_KEYS,
    COMFORT_KEYS,
)


def grouped_input(entry, **updates):
    values = {**DEFAULTS, **entry.data, **entry.options, **updates}
    names = ("comfort", "consumption")
    keys = COMFORT_KEYS | ACCOUNTING_KEYS
    return {
        name: {key: values[key] for key in SETTINGS_SECTIONS[name]
               if key in keys and values.get(key) is not None}
        for name in names
    }


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
    if energy_ready and entry.runtime_data.group_manager.repository.registry is not None:
        await attach_energy_group(hass, entry)
    return entry


async def attach_energy_group(hass, entry, **sources):
    from custom_components.solar_climate_manager.domain.groups import GroupPolicy, GroupSources

    hass.states.async_set("sensor.load", "600", {"unit_of_measurement": "W"})
    repository = entry.runtime_data.group_manager.repository
    registry = await repository.async_update(lambda state: state.create(
        "Energy", GroupSources(load_power_entity="sensor.load", soc_entity="sensor.soc",
                               battery_power_entity="sensor.battery",
                               grid_available_entity="binary_sensor.grid", **sources),
        GroupPolicy())[0])
    await repository.async_update(lambda state: state.join(
        entry.runtime_data.device_id, registry.groups[-1].group_id))
    await hass.async_block_till_done()


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
        assert not coordinator.data["invalid_data"]
        assert coordinator.data["temperature"] == 23
        assert coordinator.data["demand"]
        calls.assert_not_called()


async def test_reload_restores_hysteresis_and_options_reset(hass):
    entry = await setup(hass)
    hass.states.async_set("sensor.room", "23", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["demand"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        grouped_input(entry, target_temperature=20, hysteresis=1),
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
    await attach_energy_group(hass, entry, pv_power_entity="sensor.pv")
    assert entry.runtime_data.data["pv_power"] == 2800
    assert "forecast_power_now" not in entry.runtime_data.data
    hass.states.async_set("sensor.pv", "unavailable")
    await hass.async_block_till_done()
    assert entry.runtime_data.data["pv_power"] is None
    assert entry.runtime_data.data["demand"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        grouped_input(entry, pv_power_entity=None),
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert "pv_power_entity" not in entry.options
    assert "pv_power_entity" not in entry.runtime_data.settings


async def test_reload_removes_retired_forecast_entities(hass):
    from homeassistant.helpers import entity_registry as er

    entry = await setup(hass)
    registry = er.async_get(hass)
    retired = [
        registry.async_get_or_create(
            "sensor", DOMAIN, f"{entry.entry_id}_{key}", config_entry=entry,
        ).entity_id
        for key in ("forecast_power_now", "forecast_power_30m", "forecast_power_60m", "forecast_margin")
    ]
    temperature = registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_temperature")
    assert temperature is not None
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert all(registry.async_get(entity_id) is None for entity_id in retired)
    assert registry.async_get(temperature) is not None


async def test_optional_generation_forecast_options_reload_and_live_updates(hass):
    entry = await setup(hass)
    hass.states.async_set("sensor.forecast", "3.8", {"unit_of_measurement": "kW"})
    await attach_energy_group(hass, entry, generation_forecast_entity="sensor.forecast")
    assert entry.runtime_data.data["generation_forecast"] == 3800
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["generation_forecast"] == 3800
    hass.states.async_set("sensor.forecast", "unavailable", {"unit_of_measurement": "kW"})
    await hass.async_block_till_done()
    assert entry.runtime_data.data["generation_forecast"] is None
    form = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], grouped_input(entry, generation_forecast_entity=None))
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert "generation_forecast_entity" not in entry.runtime_data.settings
    assert entry.runtime_data.effective_settings()["generation_forecast_entity"] == "sensor.forecast"


async def test_reject_energy_sensor_as_solar_power(hass):
    from dataclasses import replace

    from custom_components.solar_climate_manager.group_flow import validate_group_sources

    first, _, repository, group_id = await setup_shadow_group(hass)
    hass.states.async_set("sensor.energy", "5", {"unit_of_measurement": "kWh"})
    with pytest.raises(ValueError, match="invalid_power"):
        validate_group_sources(hass, replace(repository.registry.group(group_id).sources,
                                            pv_power_entity="sensor.energy"))


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
    await attach_energy_group(hass, entry)
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
    await attach_energy_group(hass, entry, grid_power_entity="sensor.grid",
                              grid_import_limit_entity="number.limit")
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
        task = coordinator.commands.task
        assert task is not None
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert cancelled.is_set()
        assert task.done()
        assert coordinator.commands.task is None
        assert coordinator.commands.closed


@pytest.mark.parametrize("mode", ["disabled", "observation", "control", "temporary_block"])
async def test_v1_migration_preserves_identity_mode_options_and_signatures(hass, mode):
    from custom_components.solar_climate_manager import async_migrate_entry
    from custom_components.solar_climate_manager.const import REMOVED_SETTINGS
    from custom_components.solar_climate_manager.settings import configuration_values

    original = {**inputs(), "operation_mode": mode}
    options = {"temporary_block_date": "2026-10-15", "temporary_previous_mode": "control"}
    entry = MockConfigEntry(domain=DOMAIN, data=original, options=options,
                            unique_id="climate.test", version=1)
    entry.add_to_hass(hass)
    identity = entry.entry_id
    assert await async_migrate_entry(hass, entry)
    assert entry.version == 2
    assert entry.entry_id == identity
    assert entry.unique_id == "climate.test"
    assert entry.data["device_id"] == identity
    assert entry.data["operation_mode"] == mode
    assert dict(entry.options) == options
    assert configuration_values(entry.data, entry.options, DEFAULTS, REMOVED_SETTINGS) == configuration_values(
        original, options, DEFAULTS, REMOVED_SETTINGS)
    assert await async_migrate_entry(hass, entry)
    assert entry.data["device_id"] == identity


async def test_group_repository_real_store_preserves_members_and_reservations(hass):
    from dataclasses import replace

    from custom_components.solar_climate_manager.adapters.groups import (
        GroupRepository,
        get_group_repository,
    )
    from custom_components.solar_climate_manager.domain.groups import (
        GroupPolicy,
        GroupSources,
        UnresolvedReservation,
    )

    repository = get_group_repository(hass)
    assert get_group_repository(hass) is repository
    await repository.async_load()
    registry = await repository.async_update(lambda state: state.create(
        "House", GroupSources(), GroupPolicy())[0])
    group_id = registry.groups[0].group_id
    await repository.async_update(lambda state: state.join("one", group_id).join("two", group_id))
    await repository.async_update(lambda state: replace(state, unresolved=(
        UnresolvedReservation("one", group_id, 900),)))
    reloaded = await GroupRepository(repository.store).async_load()
    assert reloaded == repository.registry
    assert len(reloaded.memberships) == 2
    assert reloaded.unresolved[0].watts == 900


async def test_two_legacy_entries_remain_independent_after_setup_and_reload(hass):
    from custom_components.solar_climate_manager.adapters.groups import get_group_repository

    first = await setup(hass)
    hass.states.async_set("climate.second", "off", {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21})
    second = MockConfigEntry(domain=DOMAIN, data={**inputs(), "climate_entity": "climate.second"},
                            unique_id="climate.second", version=1)
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    assert first.version == second.version == 2
    assert first.runtime_data.device_id != second.runtime_data.device_id
    assert first.runtime_data.runtime is not second.runtime_data.runtime
    assert first.runtime_data.commands is not second.runtime_data.commands
    registry = await get_group_repository(hass).async_load()
    assert registry.memberships == ()
    identity = first.runtime_data.device_id
    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()
    assert first.runtime_data.device_id == identity
    assert first.runtime_data.settings["operation_mode"] == "observation"
    assert second.runtime_data.settings["operation_mode"] == "observation"


async def test_future_config_version_is_not_migrated(hass):
    from custom_components.solar_climate_manager import async_migrate_entry

    entry = MockConfigEntry(domain=DOMAIN, data=inputs(), version=3)
    entry.add_to_hass(hass)
    assert not await async_migrate_entry(hass, entry)
    assert entry.version == 3
    assert "device_id" not in entry.data


async def setup_shadow_group(hass):
    from custom_components.solar_climate_manager.adapters.groups import get_group_repository
    from custom_components.solar_climate_manager.domain.groups import GroupPolicy, GroupSources

    first = await setup(hass)
    hass.states.async_set("climate.second", "off", {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21})
    second = MockConfigEntry(domain=DOMAIN, data={**inputs(), "climate_entity": "climate.second"},
                            unique_id="climate.second", version=1)
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()
    for entity, value, unit in (("sensor.pv", "1600", "W"), ("sensor.load", "600", "W"),
                                ("sensor.soc", "95", "%"), ("sensor.battery", "0", "W")):
        hass.states.async_set(entity, value, {"unit_of_measurement": unit})
    hass.states.async_set("binary_sensor.grid", "off")
    repository = get_group_repository(hass)
    registry = await repository.async_update(lambda state: state.create(
        "House", GroupSources(pv_power_entity="sensor.pv", load_power_entity="sensor.load",
                              soc_entity="sensor.soc", battery_power_entity="sensor.battery",
                              grid_available_entity="binary_sensor.grid"),
        GroupPolicy())[0])
    group_id = registry.groups[0].group_id
    await repository.async_update(lambda state: state.join(first.runtime_data.device_id, group_id)
                                  .join(second.runtime_data.device_id, group_id))
    first.runtime_data._evaluate()
    await hass.async_block_till_done()
    return first, second, repository, group_id


async def test_group_shadow_allocation_has_no_service_calls_or_real_reservations(hass):
    from custom_components.solar_climate_manager.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    with patch.object(type(hass.services), "async_call") as calls:
        first, second, repository, group_id = await setup_shadow_group(hass)
        observer = first.runtime_data.group_observer
        result = observer.results[group_id]
        assert result["shadow"] is True
        assert result["shadow_reserved_watts"] == 900
        assert result["unresolved_reserved_watts"] == 0
        assert result["available_watts"] == 100
        assert sum(d["action"] == "start" for d in result["decisions"]) == 1
        assert repository.registry.unresolved == ()
        assert observer.states[group_id].reservations == ()
        for _ in range(3):
            second.runtime_data._evaluate()
            assert observer.results[group_id] == result
        exported = await async_get_config_entry_diagnostics(hass, first)
        assert exported["group_observation"] == result
        assert "sensor.pv" not in str(exported)
        calls.assert_not_called()
        assert hass.states.get("climate.test").state == "off"
        assert hass.states.get("climate.second").state == "off"


async def test_group_shadow_unload_blocks_new_previews_and_reload_restores_them(hass):
    first, second, repository, group_id = await setup_shadow_group(hass)
    observer = first.runtime_data.group_observer
    device_id = first.runtime_data.device_id
    assert await hass.config_entries.async_unload(first.entry_id)
    assert device_id not in observer.devices
    assert observer.results[group_id]["reason"] == "members_unavailable"
    assert observer.results[group_id]["decisions"] == []
    assert len(repository.registry.memberships) == 2
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    second.runtime_data._evaluate()
    assert observer.results[group_id]["shadow_reserved_watts"] == 900


async def test_two_shadow_groups_keep_separate_budgets(hass):
    from custom_components.solar_climate_manager.domain.groups import GroupPolicy

    first, second, repository, first_group = await setup_shadow_group(hass)
    first_config = repository.registry.group(first_group)
    registry = await repository.async_update(lambda state: state.create(
        "Workshop", first_config.sources, GroupPolicy())[0])
    second_group = registry.groups[1].group_id
    second_id = second.runtime_data.device_id
    await repository.async_update(lambda state: state.leave(second_id).join(second_id, second_group))
    first.runtime_data._evaluate()
    observer = first.runtime_data.group_observer
    assert observer.results[first_group]["shadow_reserved_watts"] == 900
    assert observer.results[second_group]["shadow_reserved_watts"] == 900
    assert len(observer.results[first_group]["decisions"]) == 1
    assert len(observer.results[second_group]["decisions"]) == 1


async def test_group_shadow_cannot_consume_or_release_durable_uncertainty(hass):
    from dataclasses import replace

    from custom_components.solar_climate_manager.domain.groups import UnresolvedReservation

    first, second, repository, group_id = await setup_shadow_group(hass)
    await repository.async_update(lambda state: replace(state, unresolved=(
        UnresolvedReservation(first.runtime_data.device_id, group_id, 900),)))
    before = repository.registry
    second.runtime_data._evaluate()
    result = first.runtime_data.group_observer.results[group_id]
    assert result["unresolved_reserved_watts"] == 900
    assert result["shadow_reserved_watts"] == 0
    assert not any(d["action"] == "start" for d in result["decisions"])
    assert repository.registry is before


async def test_group_capture_reads_each_shared_entity_once(hass):
    from collections import Counter

    first, _, _, _ = await setup_shadow_group(hass)
    original = hass.states.get
    with patch.object(type(hass.states), "get", autospec=True,
                      side_effect=lambda _, entity_id: original(entity_id)) as reads:
        first.runtime_data.group_observer.evaluate()
    counts = Counter(call.args[1] for call in reads.call_args_list)
    assert counts["sensor.pv"] == 1
    assert counts["sensor.load"] == 1
    assert counts["sensor.room"] == 1
    assert all(count == 1 for count in counts.values())


async def test_broken_group_store_does_not_break_independent_setup(hass):
    with patch("custom_components.solar_climate_manager.adapters.groups.GroupRepository.async_load",
               side_effect=ValueError("unsupported_group_schema")):
        entry = await setup(hass)
    coordinator = entry.runtime_data
    assert coordinator.data["automation_mode"] == "observation"
    assert coordinator.group_observer.diagnostics(coordinator.device_id)["reason"] == "group_store_unavailable"


def enable_group_control(*entries):
    for entry in entries:
        entry.runtime_data._set_operation_mode("control")
        entry.runtime_data._evaluate()


async def test_group_control_serializes_starts_and_persists_before_service(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    # Plenty of capacity still permits only one unconfirmed physical start.
    hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
    records = []

    async def service(domain, name, data, **kwargs):
        if name == "set_temperature":
            records.append(data)
            assert len(repository.registry.unresolved) == 1
            assert repository.registry.unresolved[0].phase == "command_pending"

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert len(records) == 1
        for _ in range(3):
            first.runtime_data._evaluate()
            second.runtime_data._evaluate()
        await hass.async_block_till_done()
        assert len(records) == 1
        assert len(repository.registry.unresolved) == 1


@pytest.mark.parametrize("change", ["soc", "mode", "target"])
async def test_group_control_revalidates_after_durable_write(hass, change):
    first, second, repository, _ = await setup_shadow_group(hass)
    save = repository.store.async_save

    async def changed_during_save(data):
        await save(data)
        if data["unresolved"]:
            if change == "soc":
                hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
            elif change == "mode":
                for entry in (first, second):
                    entry.runtime_data._set_operation_mode("observation")
            else:
                for entry in (first, second):
                    entry.runtime_data.settings["target_temperature"] = 19

    with patch.object(type(repository.store), "async_save", side_effect=changed_during_save), patch.object(
        type(hass.services), "async_call"
    ) as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        calls.assert_not_called()
        assert repository.registry.unresolved == ()


async def test_group_control_storage_failure_never_dispatches_start(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    with patch.object(type(repository.store), "async_save", side_effect=OSError("disk full")), patch.object(
        type(hass.services), "async_call"
    ) as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        calls.assert_not_called()
        assert repository.registry.unresolved == ()


async def test_group_control_shared_source_stops_running_member(hass):
    first, second, _, _ = await setup_shadow_group(hass)
    # Set the physical state before enabling control; clear the manual pause.
    hass.states.async_set("climate.test", "heat", {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21, "temperature": 25})
    await hass.async_block_till_done()
    hass.states.async_set("sensor.load", "1500", {"unit_of_measurement": "W"})
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first)
        await hass.async_block_till_done()
        calls.reset_mock()
        hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
        await hass.async_block_till_done()
        assert any(c.args[1] == "set_hvac_mode" and c.args[2]["entity_id"] == "climate.test"
                   for c in calls.call_args_list), (calls.call_args_list, first.runtime_data.group_manager.diagnostics(first.runtime_data.device_id), first.runtime_data.data, first.runtime_data.commands.task)
        assert second.runtime_data.settings["operation_mode"] == "observation"


async def test_group_control_missing_member_blocks_starts(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    assert await hass.config_entries.async_unload(second.entry_id)
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first)
        await hass.async_block_till_done()
        calls.assert_not_called()
        assert repository.registry.unresolved == ()


async def test_group_control_reload_preserves_uncertainty_and_avoids_duplicate_start(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        reserve = repository.registry.unresolved[0]
        entry = next(e for e in (first, second) if e.runtime_data.device_id == reserve.device_id)
        calls.reset_mock()
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert not any(c.args[1] == "set_temperature" for c in calls.call_args_list)
        assert any(c.args[1] == "set_hvac_mode" for c in calls.call_args_list)
        assert repository.registry.unresolved[0].command_id == reserve.command_id
        assert repository.registry.unresolved[0].stop_sent_at is not None


async def test_group_control_releases_reserve_only_after_coherent_meter_reports(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    for entry, sensor in ((first, "sensor.ac_one"), (second, "sensor.ac_two")):
        entry.runtime_data.settings["ac_power_entity"] = sensor
        hass.states.async_set(sensor, "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.load", "600", {"unit_of_measurement": "W"}, force_update=True)
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert len(records) == 1
        name, data, context = records[0]
        started = next(e for e in (first, second)
                       if e.runtime_data.settings["climate_entity"] == data["entity_id"])
        token = repository.registry.unresolved[0].command_id
        hass.states.async_set(data["entity_id"], "heat", {
            "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21,
            "temperature": data["temperature"]}, context=context)
        await hass.async_block_till_done()
        assert len(records) == 1  # Physical heat alone cannot fund the next start.
        hass.states.async_set(started.runtime_data.settings["ac_power_entity"], "900",
                              {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
        assert len(records) == 1  # Aggregate still predates the individual meter.
        hass.states.async_set("sensor.load", "1500", {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
        assert len(records) == 2, (repository.registry.unresolved, first.runtime_data.group_manager.results, first.runtime_data.group_manager.task)
        assert all(name == "set_temperature" for name, _, _ in records)
        assert records[0][1]["entity_id"] != records[1][1]["entity_id"]
        assert len(repository.registry.unresolved) == 1
        assert repository.registry.unresolved[0].command_id != token


def settle_group_measurements(hass, freezer):
    """Provide fresh aggregate readings after an estimated member has settled."""
    freezer.tick(timedelta(seconds=121))
    for entity_id in ("sensor.pv", "sensor.load", "sensor.soc", "sensor.battery",
                      "binary_sensor.grid"):
        state = hass.states.get(entity_id)
        hass.states.async_set(entity_id, state.state, dict(state.attributes), force_update=True)


async def test_group_control_slow_start_does_not_block_other_protective_stop(hass, freezer):
    first, second, repository, _ = await setup_shadow_group(hass)
    hass.states.async_set("climate.second", "heat", {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21, "temperature": 25})
    await hass.async_block_till_done()
    settle_group_measurements(hass, freezer)
    hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.load", "1500", {"unit_of_measurement": "W"})
    started, stopped, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def service(domain, name, data, **kwargs):
        if name == "set_temperature" and data["entity_id"] == "climate.test":
            started.set()
            await release.wait()
        if name == "set_hvac_mode" and data["entity_id"] == "climate.second":
            stopped.set()

    with patch.object(type(hass.services), "async_call", side_effect=service):
        try:
            enable_group_control(first, second)
            await asyncio.wait_for(started.wait(), 5)
            assert repository.registry.unresolved
            hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
            await asyncio.wait_for(stopped.wait(), 5)
            assert not release.is_set()
        finally:
            release.set()
            await hass.async_block_till_done()


async def test_group_control_failure_isolated_between_groups(hass):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.solar_climate_manager.domain.groups import GroupPolicy

    first, second, repository, first_group = await setup_shadow_group(hass)
    registry = await repository.async_update(lambda state: state.create(
        "Workshop", state.group(first_group).sources, GroupPolicy())[0])
    second_id = second.runtime_data.device_id
    await repository.async_update(lambda state: state.leave(second_id).join(second_id, registry.groups[1].group_id))
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data["entity_id"]))
        if data["entity_id"] == "climate.test":
            raise HomeAssistantError("device offline")

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert ("set_temperature", "climate.test") in records
        assert ("set_temperature", "climate.second") in records
        assert len(repository.registry.unresolved) == 2
        failed = next(r for r in repository.registry.unresolved if r.group_id == first_group)
        assert failed.phase == "uncertain"


async def test_group_control_storage_failure_does_not_block_protective_stop(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert repository.registry.unresolved
        calls.reset_mock()
        with patch.object(type(repository.store), "async_save", side_effect=OSError("disk full")):
            hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
            await hass.async_block_till_done()
        assert any(c.args[1] == "set_hvac_mode" for c in calls.call_args_list)
        assert not any(c.args[1] == "set_temperature" for c in calls.call_args_list)
        assert repository.registry.unresolved  # Off without durable proof does not release power.


async def test_group_control_three_members_prioritize_and_account_for_manual_member(hass, freezer):
    from dataclasses import replace

    first, second, repository, group_id = await setup_shadow_group(hass)
    hass.states.async_set("climate.third", "heat", {
        "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21, "temperature": 25})
    third = MockConfigEntry(domain=DOMAIN, data={**inputs(), "climate_entity": "climate.third"},
                            unique_id="climate.third", version=1)
    third.add_to_hass(hass)
    assert await hass.config_entries.async_setup(third.entry_id)
    await hass.async_block_till_done()
    await repository.async_update(lambda state: state.join(third.runtime_data.device_id, group_id))
    high = second.runtime_data.device_id
    await repository.async_update(lambda state: replace(state, memberships=tuple(
        replace(m, priority=100) if m.device_id == high else m for m in state.memberships)))
    settle_group_measurements(hass, freezer)
    hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.load", "1500", {"unit_of_measurement": "W"})
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert calls.call_count == 1
        assert calls.call_args.args[2]["entity_id"] == "climate.second"
        assert repository.registry.unresolved[0].device_id == high
        hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
        await hass.async_block_till_done()
        assert not any(c.args[2]["entity_id"] == "climate.third" for c in calls.call_args_list)
        assert third.runtime_data.settings["operation_mode"] == "observation"


async def test_group_control_manual_change_during_start_keeps_reservation(hass):
    from homeassistant.core import Context

    first, second, repository, _ = await setup_shadow_group(hass)
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data["entity_id"]))
        if name == "set_temperature":
            hass.states.async_set(data["entity_id"], "cool", {
                "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21,
                "temperature": 18}, context=Context(user_id="manual-user"))

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first, second)
        await hass.async_block_till_done()
        assert len(records) == 1
        reserve = repository.registry.unresolved[0]
        controlled = next(e for e in (first, second) if e.runtime_data.device_id == reserve.device_id)
        assert controlled.runtime_data.settings["operation_mode"] == "temporary_block"
        hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
        await hass.async_block_till_done()
        assert len(records) == 1
        assert repository.registry.unresolved


async def test_group_control_restart_rebuilds_authority_from_persisted_reserve(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        reserve = repository.registry.unresolved[0]
        manager = first.runtime_data.commands.authority
        assert await hass.config_entries.async_unload(first.entry_id)
        assert await hass.config_entries.async_unload(second.entry_id)
        assert manager.task is None
        assert not manager.devices
        assert manager._source_unsub is None
        for key in (f"{DOMAIN}.groups", f"{DOMAIN}.group_manager", f"{DOMAIN}.group_observer"):
            hass.data.pop(key, None)
        calls.reset_mock()
        assert await hass.config_entries.async_setup(first.entry_id)
        assert await hass.config_entries.async_setup(second.entry_id)
        await hass.async_block_till_done()
        recovered = first.runtime_data.group_manager.repository
        assert recovered is not repository
        assert recovered.registry.unresolved[0].command_id == reserve.command_id
        assert not any(c.args[1] == "set_temperature" for c in calls.call_args_list)
        assert any(c.args[1] == "set_hvac_mode" for c in calls.call_args_list)


async def test_group_control_off_report_during_save_is_not_dispatch_confirmation(hass):
    first, second, repository, _ = await setup_shadow_group(hass)
    for entry, sensor in ((first, "sensor.ac_one"), (second, "sensor.ac_two")):
        entry.runtime_data.settings["ac_power_entity"] = sensor
        hass.states.async_set(sensor, "0", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.load", "600", {"unit_of_measurement": "W"}, force_update=True)
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        reserve = repository.registry.unresolved[0]
        owner = next(e for e in (first, second) if e.runtime_data.device_id == reserve.device_id)
        save = repository.store.async_save

        def report_off():
            climate = hass.states.get(owner.runtime_data.settings["climate_entity"])
            hass.states.async_set(climate.entity_id, "off", dict(climate.attributes), force_update=True)
            hass.states.async_set(owner.runtime_data.settings["ac_power_entity"], "0",
                                  {"unit_of_measurement": "W"}, force_update=True)
            hass.states.async_set("sensor.load", "600", {"unit_of_measurement": "W"}, force_update=True)

        async def report_during_save(data):
            await save(data)
            if data["unresolved"] and data["unresolved"][0]["stop_sent_at"] is not None:
                report_off()

        with patch.object(type(repository.store), "async_save", side_effect=report_during_save):
            hass.states.async_set("sensor.soc", "10", {"unit_of_measurement": "%"})
            await hass.async_block_till_done()
        assert any(c.args[1] == "set_hvac_mode" for c in calls.call_args_list)
        assert repository.registry.unresolved  # Reports were older than actual off dispatch.
        report_off()
        await hass.async_block_till_done()
        assert repository.registry.unresolved == ()


async def test_group_control_unreadable_membership_never_falls_back_to_local_policy(hass):
    with patch("custom_components.solar_climate_manager.adapters.groups.GroupRepository.async_load",
               side_effect=ValueError("unsupported_group_schema")), patch.object(
                   type(hass.services), "async_call") as calls:
        entry = await setup(hass, energy_ready=True)
        await entry.runtime_data.async_set_mode("control")
        await hass.async_block_till_done()
        calls.assert_not_called()
        assert entry.runtime_data.group_manager.diagnostics(entry.runtime_data.device_id)["starts_blocked"]


async def test_group_control_unload_cancels_inflight_start_without_releasing_power(hass):
    first, _, repository, _ = await setup_shadow_group(hass)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def service(domain, name, data, **kwargs):
        if name == "set_temperature":
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first)
        await asyncio.wait_for(started.wait(), 5)
        reserve = repository.registry.unresolved[0]
        coordinator = first.runtime_data
        assert await hass.config_entries.async_unload(first.entry_id)
        await hass.async_block_till_done()
        assert cancelled.is_set()
        assert coordinator.commands.closed
        assert coordinator.commands.task is None
        assert repository.registry.unresolved[0].command_id == reserve.command_id
        assert repository.registry.unresolved[0].phase == "uncertain"


async def test_group_control_deficit_sheds_only_lower_priority_member(hass):
    from dataclasses import replace

    first, second, repository, group_id = await setup_shadow_group(hass)
    for entity in ("climate.test", "climate.second"):
        hass.states.async_set(entity, "heat", {
            "hvac_modes": ["off", "heat", "cool"], "current_temperature": 21, "temperature": 25})
    await hass.async_block_till_done()
    group = repository.registry.group(group_id)
    await repository.async_update(lambda state: state.update(replace(
        group, policy=replace(group.policy, grid_absence_delay=0))))
    await repository.async_update(lambda state: replace(state, memberships=tuple(
        replace(m, priority=10) if m.device_id == first.runtime_data.device_id else m
        for m in state.memberships)))
    hass.states.async_set("sensor.pv", "5000", {"unit_of_measurement": "W"})
    hass.states.async_set("sensor.load", "2400", {"unit_of_measurement": "W"})
    with patch.object(type(hass.services), "async_call") as calls:
        enable_group_control(first, second)
        await hass.async_block_till_done()
        calls.reset_mock()
        hass.states.async_set("sensor.pv", "1600", {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
        assert [(c.args[1], c.args[2]["entity_id"]) for c in calls.call_args_list] == [
            ("set_hvac_mode", "climate.second")]
        assert repository.registry.unresolved == ()
