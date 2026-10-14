"""Demand, data health and conservative permission diagnostics."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import SolarClimateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            SolarClimateBinarySensor(entry.runtime_data, key)
            for key in (
                "demand",
                "invalid_data",
                "control_allowed",
                "grid_available",
                "energy_allowed",
                "running",
                "manual_pause",
                "energy_data_invalid",
                "command_failed",
                "grid_import_limit_active",
            )
        ]
    )


class SolarClimateBinarySensor(SolarClimateEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return self.coordinator.data[self.key]

    @property
    def available(self):
        return super().available and (
            self.key not in ("grid_available", "running")
            or self.coordinator.data[self.key] is not None
        )

    @property
    def extra_state_attributes(self):
        if self.key == "energy_allowed":
            data = self.coordinator.data
            return {
                "reason": data["energy_reason"],
                "grid_available": data["grid_available"],
                "soc": data["soc"],
                "minimum_soc": self.coordinator.settings["minimum_soc"],
                "restart_soc": self.coordinator.settings["restart_soc"],
                "soc_blocked": data["soc_blocked"],
                "battery_power_w": data["battery_power"],
                "energy_data_invalid": data["energy_data_invalid"],
                "grid_import_limit_w": data["grid_import_limit"],
                "grid_import_margin_w": data["grid_import_margin"],
                "grid_import_limit_active": data["grid_import_limit_active"],
            }
        if self.key == "command_failed":
            return {"error": self.coordinator.data["command_error"]}
        return None
