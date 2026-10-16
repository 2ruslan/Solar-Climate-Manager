"""Solar Climate Manager: observation and real climate control."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .adapters.migrations import CONFIG_VERSION, migrate_device_data
from .const import PLATFORMS
from .coordinator import SolarClimateCoordinator
from .runtime.group import get_group_manager
from .runtime.group_observation import get_group_observer


async def async_setup(hass: HomeAssistant, config) -> bool:
    from .panel import async_setup_panel_api

    await async_setup_panel_api(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from .panel import async_show_panel

    coordinator = SolarClimateCoordinator(hass, entry)
    entry.runtime_data = coordinator
    manager = get_group_manager(hass)
    await manager.async_prepare(coordinator)
    await coordinator.async_initialize()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await get_group_observer(hass).async_register(coordinator)
    manager.register(coordinator)
    await async_show_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
        from .panel import async_hide_panel

        async_hide_panel(hass)
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Preserve entry/unique IDs, options, operation mode and legacy Store v1."""
    try:
        data = migrate_device_data(dict(entry.data), entry.version, entry.entry_id)
    except ValueError:
        return False
    hass.config_entries.async_update_entry(entry, data=data, version=CONFIG_VERSION)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Detach a removed entry only when no unresolved commitment can be lost."""
    from .adapters.groups import get_group_repository

    repository = get_group_repository(hass)
    identity = entry.data.get("device_id", entry.entry_id)
    await repository.async_update(lambda state: state if any(
        r.device_id == identity for r in state.unresolved) else state.leave(identity))
