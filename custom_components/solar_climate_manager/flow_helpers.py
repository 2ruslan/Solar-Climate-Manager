"""Shared schemas and validation for device and group forms."""

from homeassistant.helpers import selector

from .climate_control import normalized_target
from .const import OPTIONAL_SOURCES
from .settings import NUMERIC_SETTINGS, SOURCE_FLAGS, valid_policy

try:
    import probatio as vol
except ImportError:
    import voluptuous as vol

MAIN_NUMBERS = {
    "target_temperature": (5, 35, 0.5, "°C"),
    "hysteresis": (0.1, 5, 0.1, "°C"),
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
                "number"
                if key == "grid_import_limit_entity"
                else "binary_sensor"
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
    try:
        normalized_target(
            data["target_temperature"], climate.attributes, hass.config.units.temperature_unit
        )
        normalized_target(
            data["target_temperature"],
            climate.attributes,
            hass.config.units.temperature_unit,
            clamp=True,
            bounds_c=(data["ac_min_temperature"], data["ac_max_temperature"]),
        )
    except ValueError as error:
        return str(error)
    if not valid_policy(data):
        return "invalid_soc_thresholds"
    for key in OPTIONAL_SOURCES:
        entity_id = data.get(key)
        if not entity_id:
            continue
        state = hass.states.get(entity_id)
        domain = (
            "number"
            if key == "grid_import_limit_entity"
            else "binary_sensor"
            if key == "grid_available_entity"
            else "schedule"
            if key == "schedule_entity"
            else "sensor"
        )
        unit = "%" if key == "soc_entity" else "power" if domain in ("sensor", "number") else None
        if state is None or not entity_id.startswith(f"{domain}."):
            return "invalid_energy_source"
        if unit == "power" and state.attributes.get("unit_of_measurement") not in ("W", "kW"):
            return "invalid_power"
        if unit == "%" and state.attributes.get("unit_of_measurement") != "%":
            return "invalid_energy_source"
    return None
