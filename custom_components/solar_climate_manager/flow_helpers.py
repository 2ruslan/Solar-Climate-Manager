"""Shared schemas and validation for device and group forms."""

from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .climate_control import normalized_target
from .const import OPTIONAL_SOURCES
from .domain.groups import MemberPolicy
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
SETTINGS_SECTIONS = {
    "comfort": (
        "temperature_entity", "hvac_mode", "target_temperature", "hysteresis",
        "ac_min_temperature", "ac_max_temperature", "schedule_entity",
    ),
    "grid": (
        "grid_available_entity", "grid_on_means_available",
        "grid_power_entity", "grid_positive", "grid_import_limit_entity",
        "grid_absence_minutes",
    ),
    "battery": (
        "soc_entity", "minimum_soc", "restart_soc",
        "battery_power_entity", "battery_positive",
    ),
    "solar": (
        "pv_power_entity",
    ),
    "consumption": (
        "load_power_entity", "load_includes_ac", "load_includes_battery_charging",
        "ac_power_entity", "power_accounting", "estimated_ac_power",
        "power_margin_percent", "power_settle_seconds", "power_learning_enabled",
    ),
}


def grouped_settings_schema(values, keys, suggest):
    """Present existing flat settings in ordered sections without changing storage."""
    fields = {}
    for name, ordered in SETTINGS_SECTIONS.items():
        selected = [key for key in ordered if key in keys]
        if not selected:
            continue
        schema = settings_schema(values, selected)
        by_key = {marker.schema: (marker, field) for marker, field in schema.schema.items()}
        schema = vol.Schema(dict(by_key[key] for key in selected))
        schema = suggest(
            schema, {key: values[key] for key in selected if values.get(key) is not None}
        )
        fields[vol.Required(name)] = section(schema, {"collapsed": False})
    return vol.Schema(fields)


def flatten_settings_sections(user_input, keys):
    """Only accept fields exposed by this device's sections."""
    return {
        key: value
        for name, ordered in SETTINGS_SECTIONS.items()
        for key, value in user_input.get(name, {}).items()
        if key in keys and key in ordered
    }


def settings_schema(values, keys):
    fields = {}
    ordered_keys = sorted(keys)
    for source, interpretation in (
        ("grid_available_entity", "grid_on_means_available"),
        ("grid_power_entity", "grid_positive"),
    ):
        if source in keys and interpretation in keys:
            ordered_keys.remove(interpretation)
            ordered_keys.insert(ordered_keys.index(source) + 1, interpretation)
    for key in ordered_keys:
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
        elif key in ("hvac_mode", "battery_positive", "grid_positive", "power_accounting"):
            choices = {
                "hvac_mode": ["heat", "cool"],
                "battery_positive": ["charge", "discharge"],
                "grid_positive": ["import", "export"],
                "power_accounting": ["legacy", "meter", "estimated"],
            }[key]
            fields[vol.Required(key, default=values[key])] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=choices, translation_key=key)
            )
        else:
            fields[vol.Required(key, default=values[key])] = selector.BooleanSelector()
    return vol.Schema(fields)


def validate(hass, data):
    if type(data.get("power_learning_enabled", False)) is not bool:
        return "invalid_member_policy"
    try:
        MemberPolicy.from_settings(data)
    except ValueError as error:
        return "missing_power_meter" if str(error) == "missing_power_meter" else "invalid_member_policy"
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
        if key == "ac_power_entity" and data.get("power_accounting") == "estimated":
            continue
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
