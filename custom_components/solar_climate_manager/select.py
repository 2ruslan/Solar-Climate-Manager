"""One persistent three-state operation selector."""

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory

from .entity import SolarClimateEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SolarClimateModeSelect(entry.runtime_data, "operation_mode")])


class SolarClimateModeSelect(SolarClimateEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ["disabled", "observation", "control"]

    @property
    def current_option(self):
        return self.coordinator.settings["operation_mode"]

    async def async_select_option(self, option):
        if option not in self._attr_options:
            raise ValueError(option)
        await self.coordinator.async_set_mode(option)
