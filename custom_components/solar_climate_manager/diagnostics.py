"""Export non-identifying diagnostics without HA entity identifiers."""

from .presentation import build_export


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return build_export(
        coordinator.settings,
        coordinator.data,
        coordinator.manual_date,
        coordinator.previous_mode,
    )
