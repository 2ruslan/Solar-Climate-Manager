"""UI configuration; one independent config entry per climate entity."""

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, POWER_SOURCES
from .settings import BOOLEAN_SETTINGS, NUMERIC_SETTINGS, valid_policy

try:
    import probatio as vol
except ImportError:  # Compatibility with HA releases before the schema migration.
    import voluptuous as vol


def settings_schema(values):
    """Temperatures are explicitly Celsius, independently of HA display units."""
    return (
        vol.Schema(
            {
                vol.Required(
                    "target_temperature", default=values["target_temperature"]
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=35,
                        step=0.5,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("hysteresis", default=values["hysteresis"]): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0.1,
                        max=5,
                        step=0.1,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("hvac_mode", default=values["hvac_mode"]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["heat", "cool"], translation_key="hvac_mode"
                    )
                ),
                vol.Required(
                    "max_data_age", default=values["max_data_age"]
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=86400,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required("enabled", default=values["enabled"]): selector.BooleanSelector(),
                vol.Required(
                    "power_max_data_age", default=values["power_max_data_age"]
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=86400,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    "forecast_max_data_age", default=values["forecast_max_data_age"]
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=30,
                        max=86400,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        .extend(
            {
                vol.Optional(key): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                )
                for key in [
                    *POWER_SOURCES.values(),
                    "load_power_entity",
                    "battery_power_entity",
                    "grid_power_entity",
                    "ac_power_entity",
                    "soc_entity",
                    "forecast_detail_entity",
                    "forecast_updated_entity",
                ]
            }
        )
        .extend(
            {
                vol.Optional("grid_available_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="binary_sensor")
                ),
                vol.Optional("schedule_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="schedule")
                ),
                **{
                    vol.Required(key, default=values[key]): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=limits[0],
                            max=limits[1],
                            step=limits[2],
                            unit_of_measurement=limits[3],
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    )
                    for key, limits in NUMERIC_SETTINGS.items()
                },
                **{
                    vol.Required(key, default=values[key]): selector.BooleanSelector()
                    for key in BOOLEAN_SETTINGS
                },
                vol.Required(
                    "battery_positive", default=values["battery_positive"]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["charge", "discharge"], translation_key="battery_positive"
                    )
                ),
                vol.Required(
                    "grid_positive", default=values["grid_positive"]
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["import", "export"], translation_key="grid_positive"
                    )
                ),
                vol.Required(
                    "forecast_detail_attribute", default=values["forecast_detail_attribute"]
                ): selector.TextSelector(),
                vol.Required(
                    "forecast_value_attribute", default=values["forecast_value_attribute"]
                ): selector.TextSelector(),
                vol.Required(
                    "forecast_detail_unit", default=values["forecast_detail_unit"]
                ): selector.SelectSelector(selector.SelectSelectorConfig(options=["W", "kW"])),
            }
        )
    )


def validate(hass, data):
    """Check entity domains and advertised capabilities without requiring online devices."""
    climate = hass.states.get(data["climate_entity"])
    temperature = hass.states.get(data["temperature_entity"])
    if not data["climate_entity"].startswith("climate.") or climate is None:
        return "invalid_climate"
    if data["hvac_mode"] not in climate.attributes.get("hvac_modes", []):
        return "unsupported_mode"
    if not data["temperature_entity"].startswith("sensor.") or temperature is None:
        return "invalid_temperature"
    if temperature.attributes.get("unit_of_measurement") not in ("°C", "°F"):
        return "invalid_temperature"
    if not valid_policy({**DEFAULTS, **data}):
        return "invalid_soc_thresholds"
    for key in [
        *POWER_SOURCES.values(),
        "load_power_entity",
        "battery_power_entity",
        "grid_power_entity",
        "ac_power_entity",
    ]:
        entity_id = data.get(key)
        if entity_id:
            state = hass.states.get(entity_id)
            if (
                not entity_id.startswith("sensor.")
                or state is None
                or state.attributes.get("unit_of_measurement") not in ("W", "kW")
            ):
                return "invalid_power"
    for key, domain, unit in [
        ("soc_entity", "sensor", "%"),
        ("grid_available_entity", "binary_sensor", None),
        ("schedule_entity", "schedule", None),
        ("forecast_detail_entity", "sensor", None),
        ("forecast_updated_entity", "sensor", None),
    ]:
        entity_id = data.get(key)
        if entity_id:
            state = hass.states.get(entity_id)
            if (
                state is None
                or not entity_id.startswith(f"{domain}.")
                or unit is not None
                and state.attributes.get("unit_of_measurement") != unit
            ):
                return "invalid_energy_source"
    return None


class SolarClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure observation of a climate device."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            error = validate(self.hass, user_input)
            if error is None:
                await self.async_set_unique_id(user_input["climate_entity"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input["climate_entity"], data=user_input)
            errors["base"] = error
        schema = vol.Schema(
            {
                vol.Required("climate_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="climate")
                ),
                vol.Required("temperature_entity"): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
            }
        ).extend(settings_schema(DEFAULTS).schema)
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
    """Reload the coordinator after settings change."""

    async def async_step_init(self, user_input=None):
        values = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            # Missing optional fields explicitly disconnect their sources.
            merged = {**values, **user_input}
            for key in OPTIONAL_SOURCES:
                merged[key] = user_input.get(key)
            error = validate(self.hass, merged)
            if error is None:
                options = {
                    **user_input,
                    **{key: user_input.get(key) for key in OPTIONAL_SOURCES},
                }
                return self.async_create_entry(title="", data=options)
            errors["base"] = error
        schema = settings_schema(values).extend(
            {
                vol.Required(
                    "temperature_entity", default=values["temperature_entity"]
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
                ),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                user_input
                if user_input is not None
                else {key: value for key, value in values.items() if value is not None},
            ),
            errors=errors,
        )
