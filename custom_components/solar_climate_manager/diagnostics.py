"""Export non-identifying diagnostics without HA entity identifiers."""

from .presentation import build_export


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    data = build_export(
        coordinator.effective_settings(),
        coordinator.data,
        coordinator.runtime.manual_date,
        coordinator.runtime.previous_mode,
    )
    if coordinator.group_observer is not None:
        observation = coordinator.group_observer.diagnostics(coordinator.device_id)
        if observation is not None:
            data["group_observation"] = observation
    if coordinator.group_manager is not None:
        control = coordinator.group_manager.diagnostics(coordinator.device_id)
        if control is not None:
            data["group_control"] = control
    return data
