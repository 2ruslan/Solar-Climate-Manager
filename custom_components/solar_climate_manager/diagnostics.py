"""Export non-identifying diagnostics without HA entity identifiers."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "version": "0.1.1",
        "observation_only": True,
        "settings": {
            key: value for key, value in coordinator.settings.items() if not key.endswith("_entity")
        },
        "decision": coordinator.data,
    }
