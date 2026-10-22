"""Capture HA states once and normalize measurements without policy side effects."""

from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any

from ..climate_control import compensated_target, normalized_target
from ..const import OPTIONAL_SOURCES, POWER_SOURCES
from ..domain.sources import SourceReading, SourceSnapshot, SourceStatus
from ..domain.types import DeviceConfig, EnergySnapshot
from ..model import temperature_celsius
from ..power import power_watts, signed_power_watts, soc_percent
from ..strategy import house_load_power


def climate_temperature(climate: Any, attribute: str, unit: str) -> float | None:
    """Normalize a climate attribute using the caller's chosen display unit."""
    return temperature_celsius(climate.attributes.get(attribute), unit)


def _status(entity_id, state, value) -> SourceStatus:
    if not entity_id:
        return "not_configured"
    if state is None:
        return "missing"
    if state.state in ("unknown", "unavailable"):
        return "unavailable"
    return "invalid" if value is None else "valid"


def read_sources(
    get_state: Callable[[str], Any],
    settings: Mapping[str, Any],
    device: DeviceConfig,
    temperature_unit: str,
    now: datetime,
    last_temperature: float | None = None,
) -> SourceSnapshot:
    keys = ("temperature_entity", "climate_entity", *OPTIONAL_SOURCES)
    # HA State objects are immutable; the entire capture is synchronous (no awaits).
    by_id = {
        entity_id: get_state(entity_id)
        for entity_id in dict.fromkeys(settings.get(key) for key in keys)
        if entity_id
    }
    raw = {key: by_id.get(settings.get(key)) for key in keys}
    state = raw["temperature_entity"]
    climate = raw["climate_entity"]
    temperature = (
        temperature_celsius(state.state, state.attributes.get("unit_of_measurement"))
        if state
        else None
    )
    measured_temperature = temperature
    if temperature is None:
        temperature = last_temperature
    climate_valid = (
        climate is not None
        and climate.state not in ("unknown", "unavailable")
        and device.hvac_mode in climate.attributes.get("hvac_modes", [])
    )
    ac_temperature = (
        temperature_celsius(
            climate.attributes.get("current_temperature"),
            climate.attributes.get("temperature_unit", temperature_unit),
        )
        if climate_valid
        else None
    )
    raw_target = compensated_target(device.target_temperature, temperature, ac_temperature)
    ac_target = None
    if raw_target is not None:
        try:
            command_target = normalized_target(
                raw_target,
                climate.attributes,
                temperature_unit,
                clamp=True,
                bounds_c=(device.ac_min_temperature, device.ac_max_temperature),
            )
            ac_target = temperature_celsius(command_target, temperature_unit)
        except ValueError:
            pass
    data = {}
    for key, source_key in POWER_SOURCES.items():
        source = raw[source_key]
        data[key] = (
            power_watts(source.state, source.attributes.get("unit_of_measurement"))
            if source else None
        )
    for key in (
        "load_power",
        "battery_power",
        "grid_power",
        "soc",
        "ac_power",
    ):
        data[key] = _energy_value(raw[f"{key}_entity"], key)
    if data["battery_power"] is not None and settings["battery_positive"] == "charge":
        data["battery_power"] *= -1
    if data["grid_power"] is not None and settings["grid_positive"] == "export":
        data["grid_power"] *= -1
    measured_charge = max(0, -data["battery_power"]) if data["battery_power"] is not None else None
    data["battery_charge_power"] = measured_charge
    data["house_load_power"] = house_load_power(
        data["load_power"], measured_charge, settings["load_includes_battery_charging"]
    )
    limit_id = settings.get("grid_import_limit_entity")
    limit_state = raw["grid_import_limit_entity"]
    # This is a setting, not a periodically reported measurement.
    data["grid_import_limit"] = (
        power_watts(limit_state.state, limit_state.attributes.get("unit_of_measurement"))
        if limit_state
        else None
    )
    limit_active = bool(limit_id) and data["grid_import_limit"] != 0
    data["grid_import_limit_active"] = limit_active
    # Availability is a persistent binary state, not a periodic measurement.
    grid = _binary_value(raw["grid_available_entity"])
    if grid is not None and not settings["grid_on_means_available"]:
        grid = not grid
    schedule = (
        _binary_value(raw["schedule_entity"])
        if settings.get("schedule_entity")
        else True
    )
    actual_ac = data["ac_power"]
    if actual_ac is None:
        actual_ac = (
            settings["estimated_ac_power"]
            if climate and climate.attributes.get("hvac_action") in ("heating", "cooling")
            else 0
        )
    ac_valid = (not settings.get("ac_power_entity") or data["ac_power"] is not None) and data[
        "house_load_power"
    ] is not None
    snapshot = EnergySnapshot(
        pv=data["pv_power"],
        load=data["load_power"],
        soc=data["soc"],
        battery=data["battery_power"],
        grid_power=data["grid_power"],
        grid_import_limit=data["grid_import_limit"],
        grid_limit_configured=limit_active,
        grid=grid,
        actual_ac_power=actual_ac,
        ac_power_valid=ac_valid,
        temperature_valid=temperature is not None and climate_valid and ac_target is not None,
        schedule_allowed=schedule is True,
    )

    climate_available = climate is not None and climate.state not in ("unknown", "unavailable")
    ac_set_temperature = (
        climate_temperature(
            climate, "temperature", climate.attributes.get("temperature_unit", temperature_unit)
        )
        if climate_valid
        else None
    )
    normalized = {
        "temperature_entity": measured_temperature,
        "climate_entity": climate.state if climate_available else None,
        "grid_available_entity": grid,
        "schedule_entity": schedule,
    }
    normalized.update({source_key: data[key] for key, source_key in POWER_SOURCES.items()})
    normalized.update(
        {
            f"{key}_entity": data[key]
            for key in (
                "load_power",
                "battery_power",
                "grid_power",
                "soc",
                "ac_power",
                "grid_import_limit",
            )
        }
    )
    readings = {}
    for key in keys:
        source = raw[key]
        value = normalized[key] if settings.get(key) else None
        readings[key] = SourceReading(
            value,
            getattr(source, "last_reported", None),
            _status(settings.get(key), source, value),
        )
    return SourceSnapshot(
        captured_at=now,
        readings=MappingProxyType(readings),
        values=MappingProxyType(data),
        temperature=temperature,
        ac_temperature=ac_temperature,
        ac_set_temperature=ac_set_temperature,
        ac_target_temperature=ac_target,
        climate_valid=climate_valid,
        running=climate.state != "off" if climate_available else None,
        energy=snapshot,
    )


def _energy_value(state, kind):
    if state is None:
        return None
    unit = state.attributes.get("unit_of_measurement")
    value = (
        soc_percent(state.state, unit) if kind == "soc" else signed_power_watts(state.state, unit)
    )
    return (
        value
        if kind in ("battery_power", "grid_power", "soc") or value is not None and value >= 0
        else None
    )


def _binary_value(state):
    if state is None or state.state not in ("on", "off"):
        return None
    return state.state == "on"
