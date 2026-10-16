"""Explicit group options, serialized with the durable registry."""

from dataclasses import asdict, replace

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .adapters.groups import get_group_repository
from .const import DOMAIN
from .domain.groups import SHARED_SOURCE_KEYS, GroupPolicy, GroupSources
from .flow_helpers import settings_schema, vol

GROUP_FLAGS = {
    "load_includes_battery_charging",
    "grid_on_means_available",
    "battery_positive",
    "grid_positive",
}
POLICY_KEYS = {
    "minimum_soc",
    "restart_soc",
    "max_battery_discharge",
    "start_delay",
    "shortage_delay",
    "grid_absence_delay",
    "power_max_data_age",
    "grid_max_data_age",
}
ERRORS = {
    "switch_to_observation",
    "unresolved_reservation",
    "command_in_progress",
    "missing_group",
    "device_already_grouped",
    "group_has_members",
    "configuration_changed",
    "invalid_priority",
    "invalid_group_policy",
    "invalid_soc_thresholds",
    "invalid_power",
    "invalid_energy_source",
    "incomplete_sources",
    "invalid_identifier",
}


def flow_error(error):
    return (
        str(error)
        if isinstance(error, ValueError) and str(error) in ERRORS
        else "group_storage_error"
    )


def ensure_editable(hass, registry, devices, *, allow_meter_recovery=False):
    manager = hass.data.get(f"{DOMAIN}.group_manager")
    if manager and manager.mutating_devices.intersection(devices):
        raise ValueError("configuration_changed")
    if not allow_meter_recovery and any(r.device_id in devices for r in registry.unresolved):
        raise ValueError("unresolved_reservation")
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get("device_id", entry.entry_id) not in devices:
            continue
        coordinator = getattr(entry, "runtime_data", None)
        values = coordinator.settings if coordinator else {**entry.data, **entry.options}
        if values.get("operation_mode") == "control":
            raise ValueError("switch_to_observation")
        if coordinator:
            attempt = coordinator.commands.state.attempt
            unconfirmed = coordinator.commands.state.unconfirmed_start and not (
                attempt is not None and attempt.confirmed_at is not None
            )
            if coordinator.commands.task is not None or unconfirmed and not allow_meter_recovery:
                raise ValueError("command_in_progress")


def validate_group_sources(hass, sources):
    if not sources.configured:
        raise ValueError("incomplete_sources")
    for key, entity_id in asdict(sources).items():
        if entity_id is None:
            continue
        state = hass.states.get(entity_id)
        if state is None:
            raise ValueError("invalid_energy_source")
        unit = state.attributes.get("unit_of_measurement")
        if key == "soc_entity" and unit != "%":
            raise ValueError("invalid_energy_source")
        if key not in ("soc_entity", "grid_available_entity") and unit not in ("W", "kW"):
            raise ValueError("invalid_power")


def group_name(value):
    name = value.strip()
    if not 1 <= len(name) <= 255:
        raise ValueError("invalid_identifier")
    return name


def priority(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not float(value).is_integer()
        or value < 0
    ):
        raise ValueError("invalid_priority")
    return int(value)


def number(minimum=0, maximum=100000, unit=None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            **({"unit_of_measurement": unit} if unit else {}),
        )
    )


def member_schema(name=None, priority=0):
    fields = {vol.Required("priority", default=priority): number()}
    if name is not None:
        fields[vol.Required("name", default=name)] = selector.TextSelector()
    return vol.Schema(fields)


class GroupOptionsMixin:
    @property
    def device_id(self):
        return self.config_entry.data.get("device_id", self.config_entry.entry_id)

    def cached_membership(self):
        repository = getattr(self.hass, "data", {}).get(f"{DOMAIN}.groups")
        state = repository.registry if repository else None
        return state.membership(self.device_id) if state else None

    async def _registry(self):
        return await get_group_repository(self.hass).async_load()

    async def _commit(self, change, devices):
        manager = self.hass.data.get(f"{DOMAIN}.group_manager")
        gated = set()

        def guarded(state):
            affected = devices(state) if callable(devices) else devices
            ensure_editable(self.hass, state, affected)
            updated = change(state)
            if manager:
                gated.update(affected)
                manager.mutating_devices.update(gated)
            return updated

        try:
            await get_group_repository(self.hass).async_update(guarded)
        finally:
            if manager:
                manager.mutating_devices.difference_update(gated)
                manager.request_evaluation()
        # Preserve all existing options, including manual pause/return mode.
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    def _group_form(self, step, schema, values, errors=None):
        return self.async_show_form(
            step_id=step,
            errors=errors or {},
            data_schema=self.add_suggested_values_to_schema(
                schema, {k: v for k, v in values.items() if v is not None}
            ),
        )

    async def async_step_group(self, user_input=None):
        try:
            state = await self._registry()
        except (ValueError, OSError, HomeAssistantError):
            return self.async_abort(reason="group_store_unavailable")
        member = state.membership(self.device_id)
        choices = (
            ["group_member", "group_sources", "group_policy", "group_leave"]
            if member
            else ["group_join", "group_create"]
        )
        if member and state.group(member.group_id) is None:
            choices = ["group_leave"]
        if any(not any(m.group_id == g.group_id for m in state.memberships) for g in state.groups):
            choices.append("group_delete")
        return self.async_show_menu(step_id="group", menu_options=choices)

    async def async_step_group_create(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                state = await self._registry()
                ensure_editable(self.hass, state, {self.device_id})
                if state.membership(self.device_id):
                    raise ValueError("device_already_grouped")
                name = group_name(user_input["name"])
                self._draft = {"name": name, "priority": priority(user_input["priority"])}
                return await self.async_step_group_sources()
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
        return self._group_form("group_create", member_schema("", 0), user_input or {}, errors)

    async def async_step_group_join(self, user_input=None):
        state = await self._registry()
        if not state.groups:
            return self.async_abort(reason="no_groups")
        errors = {}
        if user_input is not None:
            try:
                return await self._commit(
                    lambda current: current.join(
                        self.device_id, user_input["group_id"], priority(user_input["priority"])
                    ),
                    lambda current: (
                        {self.device_id}
                        | {
                            m.device_id
                            for m in current.memberships
                            if m.group_id == user_input["group_id"]
                        }
                    ),
                )
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
        fields = {
            vol.Required("group_id"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": g.group_id, "label": g.name} for g in state.groups]
                )
            ),
            vol.Required("priority", default=0): number(),
        }
        return self._group_form("group_join", vol.Schema(fields), user_input or {}, errors)

    async def _selected(self):
        state = await self._registry()
        member = state.membership(self.device_id)
        group = state.group(member.group_id) if member else None
        if group is None:
            raise ValueError("missing_group")
        return state, member, group

    async def _edit_group(self, original, change):
        def edit(state):
            if state.group(original.group_id) != original:
                raise ValueError("configuration_changed")
            members = tuple(m for m in state.memberships if m.group_id == original.group_id)
            if getattr(self, "_original_members", members) != members:
                raise ValueError("configuration_changed")
            member = state.membership(self.device_id)
            if member is None or member.group_id != original.group_id:
                raise ValueError("configuration_changed")
            return change(state)

        return await self._commit(
            edit,
            lambda state: {
                m.device_id for m in state.memberships if m.group_id == original.group_id
            },
        )

    async def _remember_group(self, group):
        state = await self._registry()
        self._original = group
        self._original_members = tuple(
            m for m in state.memberships if m.group_id == group.group_id
        )

    async def async_step_group_member(self, user_input=None):
        try:
            state, member, group = await self._selected()
        except (ValueError, OSError, HomeAssistantError):
            return self.async_abort(reason="configuration_changed")
        errors = {}
        if user_input is None:
            await self._remember_group(group)
        else:
            try:

                def update(current):
                    renamed = current.update(replace(group, name=group_name(user_input["name"])))
                    return replace(
                        renamed,
                        memberships=tuple(
                            replace(m, priority=priority(user_input["priority"]))
                            if m.device_id == self.device_id
                            else m
                            for m in renamed.memberships
                        ),
                    )

                return await self._edit_group(self._original, update)
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
        return self._group_form(
            "group_member", member_schema(group.name, member.priority), user_input or {}, errors
        )

    async def async_step_group_sources(self, user_input=None):
        draft = getattr(self, "_draft", None)
        group = None
        if draft is not None:
            values = {**asdict(GroupSources()), **asdict(GroupPolicy()), **draft.get("sources", {})}
        else:
            try:
                _, _, group = await self._selected()
            except (ValueError, OSError, HomeAssistantError):
                return self.async_abort(reason="configuration_changed")
            values = {**asdict(group.sources), **asdict(group.policy)}
            if user_input is None:
                await self._remember_group(group)
        errors = {}
        if user_input is not None:
            try:
                sources = GroupSources(**{k: user_input.get(k) for k in SHARED_SOURCE_KEYS})
                validate_group_sources(self.hass, sources)
                flags = {k: user_input[k] for k in GROUP_FLAGS | {"load_scope"}}
                if draft is not None:
                    self._draft["sources"] = {**asdict(sources), **flags}
                    return await self.async_step_group_policy()
                return await self._edit_group(
                    self._original,
                    lambda state: state.update(
                        replace(group, sources=sources, policy=replace(group.policy, **flags))
                    ),
                )
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
            values.update(user_input)
        schema = settings_schema(values, set(SHARED_SOURCE_KEYS) | GROUP_FLAGS)
        fields = dict(schema.schema)
        fields[vol.Required("load_scope", default=values["load_scope"])] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["includes_all_members", "excludes_all_members"],
                translation_key="load_scope",
            )
        )
        return self._group_form("group_sources", vol.Schema(fields), values, errors)

    async def async_step_group_policy(self, user_input=None):
        draft = getattr(self, "_draft", None)
        group = None
        if draft is not None:
            values = asdict(GroupPolicy())
        else:
            try:
                _, _, group = await self._selected()
            except (ValueError, OSError, HomeAssistantError):
                return self.async_abort(reason="configuration_changed")
            values = asdict(group.policy)
            if user_input is None:
                await self._remember_group(group)
        errors = {}
        if user_input is not None:
            try:
                updates = {k: user_input[k] for k in POLICY_KEYS}
                if draft is not None:
                    sources = GroupSources(
                        **{k: draft["sources"].get(k) for k in SHARED_SOURCE_KEYS}
                    )
                    validate_group_sources(self.hass, sources)
                    policy = GroupPolicy(
                        **updates, **{k: draft["sources"][k] for k in GROUP_FLAGS | {"load_scope"}}
                    )

                    def create(state):
                        created, group_id = state.create(draft["name"], sources, policy)
                        return created.join(self.device_id, group_id, draft["priority"])

                    return await self._commit(create, {self.device_id})
                policy = replace(group.policy, **updates)
                return await self._edit_group(
                    self._original, lambda state: state.update(replace(group, policy=policy))
                )
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
            values.update(user_input)
        schema = vol.Schema(
            {
                vol.Required(k, default=values[k]): number(
                    maximum=100 if k in ("minimum_soc", "restart_soc") else 86400,
                    unit="%"
                    if k in ("minimum_soc", "restart_soc")
                    else "W"
                    if k == "max_battery_discharge"
                    else "s",
                )
                for k in sorted(POLICY_KEYS)
            }
        )
        return self._group_form("group_policy", schema, values, errors)

    async def async_step_group_leave(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                return await self._commit(
                    lambda state: state.leave(self.device_id), {self.device_id}
                )
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
        return self.async_show_form(
            step_id="group_leave", data_schema=vol.Schema({}), errors=errors
        )

    async def async_step_group_delete(self, user_input=None):
        state = await self._registry()
        errors = {}
        if user_input is not None:
            try:
                return await self._commit(
                    lambda current: current.delete(user_input["group_id"]), set()
                )
            except (ValueError, OSError, HomeAssistantError) as error:
                errors["base"] = flow_error(error)
        empty = [
            g for g in state.groups if not any(m.group_id == g.group_id for m in state.memberships)
        ]
        if not empty:
            return self.async_abort(reason="no_empty_groups")
        schema = vol.Schema(
            {
                vol.Required("group_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": g.group_id, "label": g.name} for g in empty]
                    )
                )
            }
        )
        return self._group_form("group_delete", schema, user_input or {}, errors)
