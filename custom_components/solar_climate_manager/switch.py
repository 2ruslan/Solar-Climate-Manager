"""Persistent observation enable switch; never controls the air conditioner."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory

from .entity import SolarClimateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SolarClimateSwitch(entry.runtime_data, "enabled")])


class SolarClimateSwitch(SolarClimateEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self):
        return self.coordinator.settings["enabled"]

    async def _set_enabled(self, enabled):
        entry = self.coordinator.entry
        self.hass.config_entries.async_update_entry(
            entry, options={**entry.options, "enabled": enabled}
        )
        self.coordinator.settings["enabled"] = enabled
        self.coordinator.signature = self.coordinator._signature()
        self.coordinator._evaluate()
        await self.hass.config_entries.async_reload(entry.entry_id)

    async def async_turn_on(self, **kwargs):
        await self._set_enabled(True)

    async def async_turn_off(self, **kwargs):
        await self._set_enabled(False)
