"""Short section-based configuration; hidden settings survive section edits."""

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, REMOVED_SETTINGS
from .settings import (
    ADVANCED_KEYS,
    COMFORT_KEYS,
    ENERGY_KEYS,
    NUMERIC_SETTINGS,
    SOURCE_FLAGS,
    merge_section,
    valid_policy,
)

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

MAIN_NUMBERS = {
    "target_temperature": (5, 35, 0.5, "°C"),
    "hysteresis": (0.1, 5, 0.1, "°C"),
    "max_data_age": (30, 86400, 1, "s"),
    "power_max_data_age": (30, 86400, 1, "s"),
    **NUMERIC_SETTINGS,
}
SOURCE_KEYS = (set(OPTIONAL_SOURCES) - {"schedule_entity"}) | SOURCE_FLAGS


def settings_schema(values, keys):
    fields = {}
    for key in sorted(keys):
        if key in MAIN_NUMBERS:
            minimum, maximum, step, unit = MAIN_NUMBERS[key]
            fields[vol.Required(key, default=values[key])] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=minimum,
                    max=maximum,
                    step=step,
                    unit_of_measurement=unit,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        elif key in OPTIONAL_SOURCES or key in ("temperature_entity", "climate_entity"):
            domain = (
                "binary_sensor"
                if key == "grid_available_entity"
                else "schedule"
                if key == "schedule_entity"
                else "climate"
                if key == "climate_entity"
                else "sensor"
            )
            config = {"domain": domain}
            if key == "temperature_entity":
                config["device_class"] = "temperature"
            marker = (
                vol.Required(key)
                if key in ("temperature_entity", "climate_entity")
                else vol.Optional(key)
            )
            fields[marker] = selector.EntitySelector(selector.EntitySelectorConfig(**config))
        elif key in ("hvac_mode", "battery_positive", "grid_positive"):
            choices = {
                "hvac_mode": ["heat", "cool"],
                "battery_positive": ["charge", "discharge"],
                "grid_positive": ["import", "export"],
            }[key]
            fields[vol.Required(key, default=values[key])] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=choices, translation_key=key)
            )
        else:
            fields[vol.Required(key, default=values[key])] = selector.BooleanSelector()
    return vol.Schema(fields)


def validate(hass, data):
    climate = hass.states.get(data["climate_entity"])
    temperature = hass.states.get(data["temperature_entity"])
    if climate is None or not data["climate_entity"].startswith("climate."):
        return "invalid_climate"
    if data["hvac_mode"] not in climate.attributes.get("hvac_modes", []):
        return "unsupported_mode"
    if (
        temperature is None
        or not data["temperature_entity"].startswith("sensor.")
        or temperature.attributes.get("unit_of_measurement") not in ("°C", "°F")
    ):
        return "invalid_temperature"
    if not valid_policy(data):
        return "invalid_soc_thresholds"
    for key in OPTIONAL_SOURCES:
        entity_id = data.get(key)
        if not entity_id:
            continue
        state = hass.states.get(entity_id)
        domain = (
            "binary_sensor"
            if key == "grid_available_entity"
            else "schedule"
            if key == "schedule_entity"
            else "sensor"
        )
        unit = "%" if key == "soc_entity" else None if domain != "sensor" else "power"
        if state is None or not entity_id.startswith(f"{domain}."):
            return "invalid_energy_source"
        if unit == "power" and state.attributes.get("unit_of_measurement") not in ("W", "kW"):
            return "invalid_power"
        if unit == "%" and state.attributes.get("unit_of_measurement") != "%":
            return "invalid_energy_source"
    return None


class SolarClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            values = {**DEFAULTS, **user_input}
            error = validate(self.hass, values)
            if error is None:
                await self.async_set_unique_id(values["climate_entity"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=values["climate_entity"], data=values)
            errors["base"] = error
        keys = (COMFORT_KEYS - {"schedule_entity"}) | {"climate_entity"}
        schema = settings_schema(DEFAULTS, keys)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarClimateOptionsFlow()


class SolarClimateOptionsFlow(config_entries.OptionsFlowWithReload):
    def __init__(self):
        self.pending = None

    def values(self):
        return {
            key: value
            for key, value in {
                **DEFAULTS,
                **self.config_entry.data,
                **self.config_entry.options,
            }.items()
            if key not in REMOVED_SETTINGS
        }

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init", menu_options=["sources", "comfort", "energy", "advanced"]
        )

    def form(self, step, keys, values, errors=None):
        schema = settings_schema(values, keys)
        suggested = {
            key: value for key, value in values.items() if key in keys and value is not None
        }
        return self.async_show_form(
            step_id=step,
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors or {},
        )

    async def section(self, step, keys, user_input):
        values = self.values()
        if user_input is not None:
            merged = merge_section(
                values,
                user_input,
                clear_sources=keys & set(OPTIONAL_SOURCES),
                removed=REMOVED_SETTINGS,
            )
            error = validate(self.hass, merged)
            if error is None:
                return self.async_create_entry(title="", data=merged)
            return self.form(step, keys, merged, {"base": error})
        return self.form(step, keys, values)

    async def async_step_sources(self, user_input=None):
        return await self.section("sources", SOURCE_KEYS, user_input)

    async def async_step_comfort(self, user_input=None):
        return await self.section("comfort", COMFORT_KEYS, user_input)

    async def async_step_advanced(self, user_input=None):
        return await self.section("advanced", ADVANCED_KEYS, user_input)

    async def async_step_energy(self, user_input=None):
        values = self.values()
        if user_input is not None:
            merged = merge_section(values, user_input, removed=REMOVED_SETTINGS)
            error = validate(self.hass, merged)
            if error:
                return self.form("energy", ENERGY_KEYS, merged, {"base": error})
            self.pending = merged
            if self.limit_keys():
                return await self.async_step_energy_limits()
            return self.async_create_entry(title="", data=merged)
        return self.form("energy", ENERGY_KEYS, values)

    def limit_keys(self):
        keys = set()
        if self.pending["allow_grid_import"]:
            keys.add("max_grid_import")
        if self.pending["prioritize_charging"]:
            keys.add("charging_reserve_power")
        return keys

    async def async_step_energy_limits(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=merge_section(self.pending, user_input))
        return self.form("energy_limits", self.limit_keys(), self.pending)
