"""Grouped configuration; hidden settings survive edits."""

from uuid import uuid4

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .adapters.groups import get_group_repository
from .adapters.migrations import CONFIG_VERSION
from .const import DEFAULTS, DOMAIN, OPTIONAL_SOURCES, REMOVED_SETTINGS
from .domain.configuration import SettingsView, device_values
from .flow_helpers import (
    flatten_settings_sections,
    grouped_settings_schema,
    settings_schema,
    validate,
    vol,
)
from .group_flow import GroupOptionsMixin, ensure_editable, flow_error
from .settings import (
    ACCOUNTING_KEYS,
    COMFORT_KEYS,
    configuration_values,
    merge_section,
)


class SolarClimateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_VERSION

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            values = {**DEFAULTS, **user_input}
            error = validate(self.hass, SettingsView(values, grouped=True))
            if error is None:
                await self.async_set_unique_id(values["climate_entity"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=values["climate_entity"], data=device_values(
                        {**values, "device_id": uuid4().hex}, grouped=True)
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
                validation_values = SettingsView(merged, grouped=True)
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
        member = self.cached_membership()
        keys = COMFORT_KEYS | ACCOUNTING_KEYS
        if user_input is not None:
            action = user_input.get("settings_action", "save")
            if action == "group":
                return await self.async_step_group()
            if action == "learning_reset" and member:
                return await self.async_step_learning_reset()
            user_input = flatten_settings_sections(user_input, keys)
        return await self.section("init", keys, user_input)

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
            return self.async_create_entry(title="", data=device_values({
                **self.values(), "power_learning_generation": uuid4().hex,
            }, grouped=True))
        self._reset_original = current
        return self.async_show_form(step_id="learning_reset", data_schema=vol.Schema({}))

    def form(self, step, keys, values, errors=None):
        self._section_original = (
            dict(self.config_entry.data), dict(self.config_entry.options), self.cached_membership()
        )
        if step == "init":
            schema = grouped_settings_schema(values, keys, self.add_suggested_values_to_schema)
            fields = dict(schema.schema)
            actions = ["save", "group"]
            if self.cached_membership() is not None:
                actions.append("learning_reset")
            fields[vol.Required("settings_action", default="save")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=actions, translation_key="settings_action",
                )
            )
            return self.async_show_form(
                step_id=step, data_schema=vol.Schema(fields), errors=errors or {},
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
                {key: value for key, value in user_input.items() if key in keys},
                clear_sources=keys & set(OPTIONAL_SOURCES),
                removed=REMOVED_SETTINGS,
            )
            validation_values = SettingsView(merged, grouped=True)
            error = None
            if member:
                registry = await self._registry()
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
                return self.async_create_entry(title="", data=device_values(merged, grouped=True))
            return self.form(step, keys, merged, {"base": error})
        return self.form(step, keys, values)

    async def async_step_sources(self, user_input=None):
        return await self.async_step_group_sources(user_input) if self.cached_membership() else await self.async_step_group()

    async def async_step_comfort(self, user_input=None):
        return await self.section("comfort", COMFORT_KEYS, user_input)

    async def async_step_advanced(self, user_input=None):
        if self.cached_membership():
            return await self.async_step_group_policy(user_input)
        return await self.async_step_group()

    async def async_step_energy(self, user_input=None):
        return await self.section("energy", ACCOUNTING_KEYS, user_input)
