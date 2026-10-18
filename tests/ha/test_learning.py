"""Learning wiring, real start acknowledgement, persistence and reset protection."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from homeassistant.util import dt as dt_util
from test_estimated_accounting import configure, prepare, report
from test_group_ui import options, submit
from test_integration import enable_group_control

from custom_components.solar_climate_manager.adapters.learning import bind_learning, learning_view
from custom_components.solar_climate_manager.domain.groups import UnresolvedReservation
from custom_components.solar_climate_manager.domain.learning import MAX_AGE
from custom_components.solar_climate_manager.panel import async_overview


async def enabled(hass):
    first, second, repository, group_id = await prepare(hass)
    assert (await configure(hass, first, power_learning_enabled=True))["type"] == "create_entry"
    await hass.async_block_till_done()
    return first, second, repository, group_id


def seed(coordinator, watts=1200):
    now = dt_util.utcnow().timestamp()
    registry = coordinator.group_manager.repository.registry
    member = registry.membership(coordinator.device_id)
    bind_learning(
        coordinator,
        registry.group(member.group_id),
        tuple(m for m in registry.memberships if m.group_id == member.group_id),
    )
    coordinator.power_learning.samples = [watts] * 3
    coordinator.power_learning.updated_at = now


async def test_real_isolated_start_collects_one_cycle(hass, freezer):
    first, _, _, _ = await enabled(hass)
    hass.states.async_set("sensor.room", "25", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    records = []

    async def service(domain, name, data, **kwargs):
        records.append((name, data, kwargs["context"]))

    with patch.object(type(hass.services), "async_call", side_effect=service):
        enable_group_control(first)
        await hass.async_block_till_done()
        for _ in range(3):
            freezer.tick(timedelta(seconds=30))
            hass.states.async_set(
                "sensor.load", "500", {"unit_of_measurement": "W"}, force_update=True
            )
            await hass.async_block_till_done()
        assert not records
        freezer.tick(timedelta(seconds=10))
        hass.states.async_set("sensor.room", "21", {"unit_of_measurement": "°C"})
        await hass.async_block_till_done()
        assert len(records) == 1
        freezer.tick(timedelta(seconds=1))
        report(hass, records[0])
        await hass.async_block_till_done()
        for _ in range(3):
            freezer.tick(timedelta(seconds=30))
            hass.states.async_set(
                "sensor.load", "1700", {"unit_of_measurement": "W"}, force_update=True
            )
            await hass.async_block_till_done()
        assert first.runtime_data.power_learning.samples == [1200]
        view = learning_view(first.runtime_data, dt_util.utcnow().timestamp())
        assert view["source"] == "configured" and view["confidence"] == "insufficient"
        assert len(records) == 1  # learning has no extra command path


async def test_learned_policy_panel_reload_and_reset(hass):
    first, _, repository, group_id = await enabled(hass)
    coordinator = first.runtime_data
    seed(coordinator)
    manager = coordinator.group_manager
    snapshot = manager._capture(repository.registry.group(group_id), repository.registry)
    own = next(r for r in snapshot.requests if r.device_id == coordinator.device_id)
    assert own.policy.planned_watts == 1440
    assert coordinator.settings["estimated_ac_power"] == 900
    panel = await async_overview(hass)
    device = next(d for d in panel["devices"] if d["device_id"] == coordinator.device_id)
    assert device["planned_power"] == 1440
    assert device["learning"]["confidence"] == "consistent"
    assert await hass.config_entries.async_reload(first.entry_id)
    await hass.async_block_till_done()
    coordinator = first.runtime_data
    assert learning_view(coordinator, dt_util.utcnow().timestamp())["learned_watts"] == 1200
    assert coordinator.power_learning.started is None
    form = await options(hass, first, "learning_reset")
    assert (await submit(hass, form, {}))["type"] == "create_entry"
    await hass.async_block_till_done()
    assert not first.runtime_data.power_learning.samples
    assert first.runtime_data.settings["power_learning_enabled"] is True
    assert first.runtime_data.settings["estimated_ac_power"] == 900


async def test_reset_cancel_stale_and_control_protection(hass):
    first, _, _, _ = await enabled(hass)
    seed(first.runtime_data)
    form = await options(hass, first, "learning_reset")
    hass.config_entries.options.async_abort(form["flow_id"])
    assert first.runtime_data.power_learning.samples
    old = await options(hass, first, "learning_reset")
    assert (await configure(hass, first, estimated_ac_power=1000, power_learning_enabled=True))[
        "type"
    ] == "create_entry"
    await hass.async_block_till_done()
    assert (await submit(hass, old, {}))["reason"] == "configuration_changed"
    first.runtime_data._set_operation_mode("control")
    form = await options(hass, first, "learning_reset")
    assert (await submit(hass, form, {}))["errors"]["base"] == "switch_to_observation"


async def test_reset_preserves_unresolved_reservation(hass):
    first, _, repository, group_id = await enabled(hass)
    seed(first.runtime_data)
    reserve = UnresolvedReservation(first.runtime_data.device_id, group_id, 1440)
    await repository.async_update(lambda state: replace(state, unresolved=(reserve,)))
    form = await options(hass, first, "learning_reset")
    assert (await submit(hass, form, {}))["errors"]["base"] == "unresolved_reservation"
    assert repository.registry.unresolved == (reserve,)
    assert first.runtime_data.power_learning.samples == [1200] * 3


async def test_unsupported_scope_config_change_and_expiry_fall_back(hass, freezer):
    first, _, repository, group_id = await enabled(hass)
    coordinator = first.runtime_data
    seed(coordinator)
    freezer.tick(timedelta(seconds=MAX_AGE + 1))
    assert learning_view(coordinator, dt_util.utcnow().timestamp())["effective_watts"] == 900
    seed(coordinator)
    group = repository.registry.group(group_id)
    await repository.async_update(
        lambda state: state.update(
            replace(group, policy=replace(group.policy, load_scope="excludes_all_members"))
        )
    )
    await hass.async_block_till_done()
    view = learning_view(coordinator, dt_util.utcnow().timestamp())
    assert view["status"] == "unsupported" and view["effective_watts"] == 900
    assert not coordinator.power_learning.samples


async def test_other_running_member_and_stale_battery_reject_cycle(hass):
    first, second, repository, group_id = await enabled(hass)
    coordinator = first.runtime_data
    manager = coordinator.group_manager
    coordinator.settings["operation_mode"] = "control"
    hass.states.async_set(
        second.data["climate_entity"],
        "heat",
        {
            "hvac_modes": ["off", "heat", "cool"],
            "current_temperature": 21,
            "temperature": 25,
        },
    )
    await hass.async_block_till_done()
    assert coordinator.power_learning.status == "ineligible"
    group = repository.registry.group(group_id)
    await repository.async_update(
        lambda state: state.update(
            replace(group, policy=replace(group.policy, load_includes_battery_charging=True))
        )
    )
    hass.states.async_set("sensor.battery", "unavailable")
    manager.request_evaluation()
    await hass.async_block_till_done()
    assert coordinator.power_learning.status == "ineligible"
    assert not coordinator.power_learning.samples
