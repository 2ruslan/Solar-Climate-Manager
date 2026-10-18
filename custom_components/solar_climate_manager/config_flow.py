"""Short section-based configuration; hidden settings survive section edits."""

from dataclasses import asdict
from uuid import uuid4

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .adapters.groups import get_group_repository
from .adapters.migrations import CONFIG_VERSION
from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, REMOVED_SETTINGS
from .flow_helpers import SOURCE_KEYS, settings_schema, validate, vol
from .group_flow import GroupOptionsMixin, ensure_editable, flow_error
from .settings import (
    ACCOUNTING_KEYS,
    ADVANCED_KEYS,
    COMFORT_KEYS,
    ENERGY_KEYS,
    configuration_values,
    merge_section,
)


class SolarClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_VERSION

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            values = {**DEFAULTS, **user_input}
            error = validate(self.hass, values)
            if error is None:
                await self.async_set_unique_id(values["climate_entity"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=values["climate_entity"], data={**values, "device_id": uuid4().hex}
                )
            errors["base"] = error
        keys = (COMFORT_KEYS - {"schedule_entity"}) | {"climate_entity"}
        schema = settings_schema(DEFAULTS, keys)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        values = configuration_values(entry.data, entry.options, DEFAULTS, REMOVED_SETTINGS)
        errors = {}
        if user_input is not None:
            merged = {**values, **user_input}
            error = None
            try:
                registry = await get_group_repository(self.hass).async_load()
                identity = entry.data.get("device_id", entry.entry_id)
                ensure_editable(self.hass, registry, {identity})
                member = registry.membership(identity)
                group = registry.group(member.group_id) if member else None
                validation_values = (
                    {**merged, **asdict(group.sources), **asdict(group.policy)} if group else merged
                )
                error = validate(self.hass, validation_values)
            except (ValueError, OSError, HomeAssistantError) as failure:
                error = flow_error(failure)
            if error is None:
                for other in self._async_current_entries():
                    effective = {**other.data, **other.options}
                    if (
                        other.entry_id != entry.entry_id
                        and effective.get("climate_entity") == merged["climate_entity"]
                    ):
                        error = "already_configured"
                        break
            if error is None:
                updates = {
                    key: merged[key]
                    for key in ("climate_entity", "temperature_entity", "hvac_mode")
                }
                manager = self.hass.data.get(f"{DOMAIN}.group_manager")
                if manager:
                    manager.mutating_devices.add(identity)
                try:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, **updates},
                        options={**entry.options, **updates},
                        unique_id=merged["climate_entity"],
                        title=merged["climate_entity"],
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                finally:
                    if manager:
                        manager.mutating_devices.discard(identity)
                        manager.request_evaluation()
                return self.async_abort(reason="reconfigure_successful")
            errors["base"] = error
            values = merged
        return self.async_show_form(
            step_id="reconfigure",
            errors=errors,
            data_schema=self.add_suggested_values_to_schema(
                settings_schema(values, {"climate_entity", "temperature_entity", "hvac_mode"}),
                values,
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolarClimateOptionsFlow()


class SolarClimateOptionsFlow(GroupOptionsMixin, config_entries.OptionsFlowWithReload):
    def values(self):
        return configuration_values(
            self.config_entry.data, self.config_entry.options, DEFAULTS, REMOVED_SETTINGS
        )

    async def async_step_init(self, user_input=None):
        choices = ["sources", "comfort", "energy"]
        if self.cached_membership() is None:
            choices.append("advanced")
        if self.cached_membership() is not None:
            choices.append("learning_reset")
        return self.async_show_menu(step_id="init", menu_options=[*choices, "group"])

    async def async_step_learning_reset(self, user_input=None):
        current = (dict(self.config_entry.data), dict(self.config_entry.options), self.cached_membership())
        if user_input is not None:
            if getattr(self, "_reset_original", current) != current:
                return self.async_abort(reason="configuration_changed")
            try:
                registry = await self._registry()
                ensure_editable(self.hass, registry, {self.device_id})
            except (ValueError, OSError, HomeAssistantError) as error:
                return self.async_show_form(step_id="learning_reset", data_schema=vol.Schema({}),
                                            errors={"base": flow_error(error)})
            return self.async_create_entry(title="", data={
                **self.values(), "power_learning_generation": uuid4().hex,
            })
        self._reset_original = current
        return self.async_show_form(step_id="learning_reset", data_schema=vol.Schema({}))

    def form(self, step, keys, values, errors=None):
        self._section_original = (
            dict(self.config_entry.data), dict(self.config_entry.options), self.cached_membership()
        )
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
        member = self.cached_membership()
        if member:
            if step == "sources":
                keys = {"ac_power_entity"}
            elif step == "energy":
                keys = ACCOUNTING_KEYS
        if user_input is not None:
            current = (dict(self.config_entry.data), dict(self.config_entry.options), member)
            if getattr(self, "_section_original", current) != current:
                return self.async_abort(reason="configuration_changed")
            merged = merge_section(
                values,
                user_input,
                clear_sources=keys & set(OPTIONAL_SOURCES),
                removed=REMOVED_SETTINGS,
            )
            validation_values = merged
            error = None
            if member:
                registry = await self._registry()
                group = registry.group(member.group_id)
                if group:
                    validation_values = {**merged, **asdict(group.sources), **asdict(group.policy)}
                if any(
                    merged.get(key) != values.get(key)
                    for key in (*ACCOUNTING_KEYS, "temperature_entity")
                ):
                    try:
                        recovery = (
                            values.get("ac_power_entity") is None
                            and merged.get("ac_power_entity") is not None
                            and merged.get("temperature_entity") == values.get("temperature_entity")
                            and all(merged.get(key) == values.get(key) for key in ACCOUNTING_KEYS - {"ac_power_entity"})
                        )
                        ensure_editable(
                            self.hass, registry, {self.device_id}, allow_meter_recovery=recovery
                        )
                    except ValueError as failure:
                        error = flow_error(failure)
            error = error or validate(self.hass, validation_values)
            if error is None:
                return self.async_create_entry(title="", data=merged)
            return self.form(step, keys, merged, {"base": error})
        return self.form(step, keys, values)

    async def async_step_sources(self, user_input=None):
        return await self.section("sources", SOURCE_KEYS, user_input)

    async def async_step_comfort(self, user_input=None):
        return await self.section("comfort", COMFORT_KEYS, user_input)

    async def async_step_advanced(self, user_input=None):
        if self.cached_membership():
            return await self.async_step_group_policy(user_input)
        return await self.section("advanced", ADVANCED_KEYS, user_input)

    async def async_step_energy(self, user_input=None):
        return await self.section("energy", ENERGY_KEYS, user_input)
