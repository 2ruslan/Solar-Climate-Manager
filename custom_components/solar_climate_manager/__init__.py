"""Solar Climate Manager: observation and real climate control."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .adapters.migrations import CONFIG_VERSION, migrate_device_data
from .const import PLATFORMS
from .coordinator import SolarClimateCoordinator
from .runtime.group import get_group_manager
from .runtime.group_observation import get_group_observer


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SolarClimateCoordinator(hass, entry)
    entry.runtime_data = coordinator
    manager = get_group_manager(hass)
    await manager.async_prepare(coordinator)
    await coordinator.async_initialize()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await get_group_observer(hass).async_register(coordinator)
    manager.register(coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Preserve entry/unique IDs, options, operation mode and legacy Store v1."""
    try:
        data = migrate_device_data(dict(entry.data), entry.version, entry.entry_id)
    except ValueError:
        return False
    hass.config_entries.async_update_entry(entry, data=data, version=CONFIG_VERSION)
    return True
