"""Real panel lifecycle, authenticated APIs, serialized forms and stale edits."""

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant.components.frontend import DATA_PANELS
from homeassistant.helpers import entity_registry as er
from test_group_ui import group_sources, policy
from test_integration import setup, setup_shadow_group

from custom_components.solar_climate_manager.const import DOMAIN
from custom_components.solar_climate_manager.panel import (
    ASSET_PATH,
    PANEL_PATH,
    async_overview,
)

BASE = "/api/config/config_entries/options/flow"


async def post(client, url, data):
    response = await client.post(url, json=data)
    assert response.status == 200, await response.text()
    return await response.json()


async def start(client, entry, step):
    flow = await post(client, BASE, {"handler": entry.entry_id})
    for choice in (["group", step] if step.startswith("group_") else [step]):
        flow = await post(client, f"{BASE}/{flow['flow_id']}", {"next_step_id": choice})
    return flow


async def test_panel_registers_once_and_survives_partial_unload(hass):
    first, second, _, _ = await setup_shadow_group(hass)
    panel = hass.data[DATA_PANELS][PANEL_PATH]
    assert panel.require_admin is True
    assert panel.config["_panel_custom"]["module_url"].startswith(ASSET_PATH)
    assert await hass.config_entries.async_unload(first.entry_id)
    assert hass.data[DATA_PANELS][PANEL_PATH] is panel
    assert await hass.config_entries.async_unload(second.entry_id)
    assert PANEL_PATH not in hass.data[DATA_PANELS]
    assert await hass.config_entries.async_setup(first.entry_id)
    assert PANEL_PATH in hass.data[DATA_PANELS]
    assert await hass.config_entries.async_reload(first.entry_id)
    assert PANEL_PATH in hass.data[DATA_PANELS]


async def test_overview_is_admin_only_and_does_not_dispatch(hass, hass_ws_client, hass_read_only_access_token):
    first, _, repository, group_id = await setup_shadow_group(hass)
    client = await hass_ws_client(hass)
    with patch.object(type(hass.services), "async_call") as calls:
        await client.send_json_auto_id({"type": f"{DOMAIN}/overview", "include_translations": True, "language": "uk"})
        result = await client.receive_json()
        assert result["success"] is True
        overview = result["result"]
        assert overview["groups"][0]["group_id"] == group_id
        assert len(overview["devices"]) == 2
        assert overview["translations"]["options"]["step"]["energy"]["title"] == "Енергетика"
        assert overview["devices"][0]["mode_entity"]
        assert overview["devices"][0]["temperature"] == 21
        calls.assert_not_called()
        assert not repository.registry.unresolved
    readonly = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    await readonly.send_json_auto_id({"type": f"{DOMAIN}/overview"})
    assert (await readonly.receive_json())["error"]["code"] == "unauthorized"
    assert first.runtime_data.settings["operation_mode"] == "observation"


async def test_overview_uses_renamed_entity_and_unavailable_member(hass):
    first, second, _, _ = await setup_shadow_group(hass)
    entities = er.async_get(hass)
    old = entities.async_get_entity_id("select", DOMAIN, f"{first.entry_id}_operation_mode")
    entities.async_update_entity(old, new_entity_id="select.living_room_mode")
    assert await hass.config_entries.async_unload(second.entry_id)
    overview = await async_overview(hass)
    assert overview["devices"][0]["mode_entity"] == "select.living_room_mode"
    assert overview["devices"][1]["loaded"] is False
    assert overview["devices"][1]["temperature"] is None
    assert overview["groups"][0]["members"]


async def test_broken_registry_is_visible_without_empty_overwrite(hass):
    first = await setup(hass)
    manager = first.runtime_data.group_manager
    manager.repository.registry = None
    with patch.object(type(manager.repository.store), "async_load", return_value={"schema_version": 999}):
        result = await async_overview(hass)
        assert result["error"] == "group_store_unavailable"
        assert result["devices"][0]["edit_block"] == "group_store_unavailable"
        assert manager.repository.registry is None


async def test_panel_assets_and_http_group_wizard_share_existing_operations(hass, hass_client):
    first, second, repository, old_group = await setup_shadow_group(hass)
    await repository.async_update(lambda s: s.leave(first.runtime_data.device_id).leave(second.runtime_data.device_id).delete(old_group))
    client = await hass_client()
    asset = await client.get(f"{ASSET_PATH}/panel.js")
    assert asset.status == 200
    assert 'customElements.define("solar-climate-panel"' in await asset.text()
    flow = await start(client, first, "group_create")
    forms = {"group_create": flow}
    schema = {f["name"]: f for f in flow["data_schema"]}
    assert schema["priority"]["selector"]["number"]["min"] == 0
    flow = await post(client, f"{BASE}/{flow['flow_id']}", {"name": "Будинок", "priority": 5})
    forms["group_sources"] = flow
    assert not repository.registry.groups
    flow = await post(client, f"{BASE}/{flow['flow_id']}", group_sources())
    forms["group_policy"] = flow
    assert not repository.registry.groups
    flow = await post(client, f"{BASE}/{flow['flow_id']}", policy())
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()
    group_id = repository.registry.membership(first.runtime_data.device_id).group_id
    flow = await start(client, second, "group_join")
    forms["group_join"] = flow
    flow = await post(client, f"{BASE}/{flow['flow_id']}", {"group_id": group_id, "priority": 1})
    assert flow["type"] == "create_entry"
    await hass.async_block_till_done()
    flow = await start(client, first, "energy")
    forms["energy"] = flow
    assert (await client.delete(f"{BASE}/{flow['flow_id']}")).status == 200
    # Optional local fixture for browser QA; no production data or credentials.
    payload = {"overview": await async_overview(hass), "forms": forms}
    await hass.async_add_executor_job(Path("/tmp/scm-panel-fixture.json").write_text,
                                    json.dumps(payload, ensure_ascii=False), "utf-8")


async def test_http_cancel_and_stale_form_do_not_overwrite_settings(hass, hass_client):
    entry = await setup(hass)
    client = await hass_client()
    old = await start(client, entry, "energy")
    new = await start(client, entry, "energy")
    saved = await post(client, f"{BASE}/{new['flow_id']}", {"estimated_ac_power": 1200, "minimum_soc": 85, "restart_soc": 90})
    assert saved["type"] == "create_entry"
    await hass.async_block_till_done()
    stale = await post(client, f"{BASE}/{old['flow_id']}", {"estimated_ac_power": 1500, "minimum_soc": 85, "restart_soc": 90})
    assert stale["type"] == "abort" and stale["reason"] == "configuration_changed"
    assert entry.runtime_data.settings["estimated_ac_power"] == 1200
    cancelled = await start(client, entry, "comfort")
    assert (await client.delete(f"{BASE}/{cancelled['flow_id']}")).status == 200
    assert entry.runtime_data.settings["estimated_ac_power"] == 1200


async def test_http_mutations_require_administrator(hass, hass_client, hass_read_only_access_token):
    entry = await setup(hass)
    client = await hass_client(hass_read_only_access_token)
    assert (await client.get("/api/")).status == 200
    response = await client.post(BASE, json={"handler": entry.entry_id})
    assert response.status == 401


async def test_http_add_and_reconfigure_routes(hass, hass_client):
    entry = await setup(hass)
    client = await hass_client()
    base = "/api/config/config_entries/flow"
    added = await post(client, base, {"handler": DOMAIN})
    assert added["step_id"] == "user"
    assert (await client.delete(f"{base}/{added['flow_id']}")).status == 200
    changed = await post(client, base, {"handler": DOMAIN, "entry_id": entry.entry_id})
    assert changed["step_id"] == "reconfigure"
    assert (await client.delete(f"{base}/{changed['flow_id']}")).status == 200


async def test_concurrent_priority_edit_is_detected(hass, hass_client):
    first, _, repository, _ = await setup_shadow_group(hass)
    client = await hass_client()
    old = await start(client, first, "group_member")
    new = await start(client, first, "group_member")
    await post(client, f"{BASE}/{new['flow_id']}", {"name": "House", "priority": 4})
    await hass.async_block_till_done()
    stale = await post(client, f"{BASE}/{old['flow_id']}", {"name": "House", "priority": 2})
    assert stale["errors"]["base"] == "configuration_changed"
    assert repository.registry.membership(first.runtime_data.device_id).priority == 4
