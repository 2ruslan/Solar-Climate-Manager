"""Export non-identifying diagnostics without HA entity identifiers."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "version": "0.4.1",
        "settings": {
            key: value for key, value in coordinator.settings.items() if not key.endswith("_entity")
        },
        "decision": coordinator.data,
        "manual_until_date": coordinator.manual_date,
        "mode_after_temporary_block": coordinator.previous_mode,
    }
