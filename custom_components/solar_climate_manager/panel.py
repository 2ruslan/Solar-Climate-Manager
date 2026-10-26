"""Admin panel and read-only overview; mutations use HA's existing flow APIs."""

import asyncio
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .adapters.groups import get_group_repository
from .adapters.learning import learning_view
from .const import DEFAULTS, DOMAIN, REMOVED_SETTINGS
from .domain.groups import MemberPolicy
from .flow_helpers import vol
from .group_flow import ensure_editable
from .history import MAX_AGE, MAX_ROWS, SAMPLE_INTERVAL
from .settings import configuration_values

PANEL_PATH = "solar-climate-manager"
ASSET_PATH = "/solar_climate_manager_static"
PANEL_KEY = f"{DOMAIN}.panel"
VERSION = "0.8.1"


async def async_setup_panel_api(hass):
    """Register static assets and the read endpoint once per HA lifetime."""
    if PANEL_KEY in hass.data:
        return
    root = Path(__file__).parent

    def translations():
        return {lang: json.loads((root / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
                for lang in ("en", "uk")}

    labels = await hass.async_add_executor_job(translations)
    script = await hass.async_add_executor_job((root / "frontend" / "panel.js").read_bytes)
    asset_revision = hashlib.sha256(script).hexdigest()[:16]
    await hass.http.async_register_static_paths([
        StaticPathConfig(ASSET_PATH, str(root / "frontend"), cache_headers=False),
    ])
    hass.data[PANEL_KEY] = {
        "translations": labels, "lock": asyncio.Lock(), "registered": False,
        "asset_revision": asset_revision,
    }
    websocket_api.async_register_command(hass, websocket_overview)
    websocket_api.async_register_command(hass, websocket_history)


async def async_show_panel(hass):
    state = hass.data[PANEL_KEY]
    async with state["lock"]:
        if state["registered"]:
            return
        await panel_custom.async_register_panel(
            hass, frontend_url_path=PANEL_PATH, webcomponent_name="solar-climate-panel",
            sidebar_title="Solar Climate Manager", sidebar_icon="mdi:home-thermometer-outline",
            module_url=f"{ASSET_PATH}/panel.js?v={state['asset_revision']}", require_admin=True,
            config_panel_domain=DOMAIN,
        )
        state["registered"] = True


def async_hide_panel(hass):
    state = hass.data.get(PANEL_KEY)
    manager = hass.data.get(f"{DOMAIN}.group_manager")
    if state and state["registered"] and not (manager and manager.devices):
        frontend.async_remove_panel(hass, PANEL_PATH)
        state["registered"] = False


def _block(hass, registry, identities):
    try:
        ensure_editable(hass, registry, identities)
    except ValueError as error:
        return str(error)
    return None


async def async_overview(hass):
    """Copy a consistent, JSON-only overview without initiating control work."""
    repository = get_group_repository(hass)
    error = None
    try:
        registry = await repository.async_load()
    except (ValueError, OSError, HomeAssistantError):
        registry = None
        error = "group_store_unavailable"
    manager = hass.data.get(f"{DOMAIN}.group_manager")
    entities = er.async_get(hass)
    devices = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        identity = entry.data.get("device_id", entry.entry_id)
        coordinator = getattr(entry, "runtime_data", None)
        loaded = bool(entry.state is ConfigEntryState.LOADED and coordinator and not coordinator.commands.closed)
        settings = coordinator.settings if loaded else configuration_values(
            entry.data, entry.options, DEFAULTS, REMOVED_SETTINGS,
        )
        data = coordinator.data if loaded else {}
        data = data or {}
        member = registry.membership(identity) if registry else None
        climate = hass.states.get(settings["climate_entity"])
        mode_entity = entities.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_operation_mode")
        # Unique IDs use the entry ID; never guess an entity's user-editable name.
        policy = MemberPolicy.from_settings(settings)
        learning = learning_view(coordinator, dt_util.utcnow().timestamp()) if loaded else None
        devices.append({
            "device_id": identity, "entry_id": entry.entry_id,
            "name": climate.attributes.get("friendly_name", entry.title) if climate else entry.title,
            "climate_entity": settings["climate_entity"],
            "loaded": loaded, "group_id": member.group_id if member else None,
            "priority": member.priority if member else 0,
            "mode": settings["operation_mode"], "mode_entity": mode_entity,
            "temperature": data.get("temperature"), "target": settings["target_temperature"],
            "running": data.get("running") if loaded else None,
            "power_accounting": policy.power_accounting,
            "planned_power": learning["effective_watts"]
            if learning and policy.power_accounting == "estimated" else policy.planned_watts,
            "learning": learning,
            "measured_power": data.get("ac_power") if policy.power_accounting != "estimated" else None,
            "action": data.get("group_action") if member else data.get("strategy_action"),
            "reason": data.get("group_reason") if member else data.get("strategy_reason"),
            "command_status": data.get("group_command_status"),
            "edit_block": error or (_block(hass, registry, {identity}) if registry else None),
        })
    groups = []
    if registry:
        for group in registry.groups:
            members = [m for m in registry.memberships if m.group_id == group.group_id]
            sample = next((d for d in devices if d["group_id"] == group.group_id and d["loaded"]), None)
            public = manager.public_state(manager.devices[sample["device_id"]]) if manager and sample and sample["device_id"] in manager.devices else {}
            snapshot = manager.snapshots.get(group.group_id) if manager else None
            groups.append({
                "group_id": group.group_id, "name": group.name,
                "members": [asdict(m) for m in members],
                "available_power": public.get("group_available_power"),
                "load_power": public.get("group_load_power"),
                "reserved_power": public.get("group_reserved_power"),
                "unlimited": bool(snapshot and snapshot.energy.grid and (
                    not snapshot.energy.grid_limit_configured or snapshot.energy.grid_import_limit == 0)),
                "edit_block": _block(hass, registry, {m.device_id for m in members}),
                "has_reservations": any(r.group_id == group.group_id for r in registry.unresolved),
            })
    return {"version": VERSION, "devices": devices, "groups": groups, "error": error}


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/overview",
    vol.Optional("language", default="en"): str,
    vol.Optional("include_translations", default=False): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_overview(hass, connection, msg):
    result = await async_overview(hass)
    if msg["include_translations"]:
        lang = "uk" if msg["language"].startswith("uk") else "en"
        result["translations"] = hass.data[PANEL_KEY]["translations"][lang]
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/history",
    vol.Required("entry_id"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_history(hass, connection, msg):
    entry = next((entry for entry in hass.config_entries.async_entries(DOMAIN)
                  if entry.entry_id == msg["entry_id"]), None)
    coordinator = getattr(entry, "runtime_data", None)
    if not entry or entry.state is not ConfigEntryState.LOADED or not coordinator:
        connection.send_error(msg["id"], "not_loaded", "Device is not loaded")
        return
    now = dt_util.utcnow().timestamp()
    connection.send_result(msg["id"], {
        "version": VERSION, "entry_id": entry.entry_id,
        "generated_at": now, "max_age_seconds": MAX_AGE,
        "max_rows": MAX_ROWS, "rows": coordinator.history.read(now),
        "sample_interval_seconds": SAMPLE_INTERVAL,
        "events_dropped_through": coordinator.history.events_dropped_through,
    })
