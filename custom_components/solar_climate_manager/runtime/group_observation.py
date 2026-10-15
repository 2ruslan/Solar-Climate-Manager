"""Read-only group previews; never feeds decisions into the physical executor."""

import logging
from dataclasses import asdict, replace
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from ..adapters.groups import get_group_repository
from ..adapters.sources import read_sources
from ..domain.allocator import (
    AllocationState,
    DeviceRequest,
    GroupSnapshot,
    Reservation,
    allocate,
)
from ..domain.groups import MemberPolicy
from ..domain.types import DeviceConfig
from ..model import evaluate

LOGGER = logging.getLogger(__name__)


class GroupObserver:
    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self.repository = get_group_repository(hass)
        self.devices: dict[str, Any] = {}
        self.states: dict[str, AllocationState] = {}
        self.configs: dict[str, Any] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.error: str | None = None

    async def async_register(self, coordinator: Any) -> None:
        try:
            await self.repository.async_load()
        except (ValueError, OSError, HomeAssistantError):
            # Broken optional preview data must not disable independent operation.
            self.error = "group_store_unavailable"
            LOGGER.exception("Unable to load group observation configuration")
        self.devices[coordinator.device_id] = coordinator
        coordinator.group_observer = self
        self.evaluate()

    def unregister(self, coordinator: Any) -> None:
        device_id = coordinator.device_id
        if self.devices.get(device_id) is coordinator:
            self.devices.pop(device_id)
        coordinator.group_observer = None
        self.evaluate()

    def evaluate(self) -> None:
        registry = self.repository.registry
        if registry is None:
            return
        self.error = None
        now = dt_util.utcnow()
        # One synchronous HA capture across the entire preview; repeated/shared
        # entities are read once even when used by multiple members/groups.
        cache: dict[str, Any] = {}

        def get_state(entity_id: str) -> Any:
            if entity_id not in cache:
                cache[entity_id] = self.hass.states.get(entity_id)
            return cache[entity_id]

        results: dict[str, dict[str, Any]] = {}
        for group in registry.groups:
            members = tuple(m for m in registry.memberships if m.group_id == group.group_id)
            ready = registry.readiness(group.group_id, frozenset(self.devices))
            if ready not in ("configured", "unresolved_reservation"):
                results[group.group_id] = {"shadow": True, "reason": ready, "decisions": []}
                # Gaps/reload/config changes require a new start confirmation window.
                previous = self.states.get(group.group_id, AllocationState(group.group_id))
                self.states[group.group_id] = replace(
                    previous, confirmations=(), deficit_since=None, grid_absent_since=None
                )
                continue
            signature = (group, members)
            previous = self.states.get(group.group_id, AllocationState(group.group_id))
            if self.configs.get(group.group_id) != signature:
                previous = AllocationState(group.group_id, soc_blocked=previous.soc_blocked)
            self.configs[group.group_id] = signature
            # Durable uncertainties are real; hypothetical starts are never persisted
            # or carried forward as real commitments on the next observation cycle.
            previous = replace(
                previous,
                reservations=tuple(
                    Reservation(r.device_id, r.watts, now.timestamp(), phase="uncertain")
                    for r in registry.unresolved
                    if r.group_id == group.group_id
                ),
            )
            requests = []
            captured = None
            for member in members:
                coordinator = self.devices[member.device_id]
                settings = {**coordinator.settings, **asdict(group.policy), **asdict(group.sources)}
                settings["load_includes_ac"] = group.policy.load_scope == "includes_all_members"
                source = read_sources(
                    get_state,
                    settings,
                    DeviceConfig.from_settings(settings),
                    self.hass.config.units.temperature_unit,
                    now,
                )
                captured = source
                demand = evaluate(
                    source.temperature,
                    target=settings["target_temperature"],
                    hysteresis=settings["hysteresis"],
                    mode=settings["hvac_mode"],
                    previous_demand=coordinator.runtime.demand,
                    climate_valid=source.climate_valid and source.ac_target_temperature is not None,
                )
                power = source.readings["ac_power_entity"]
                climate = get_state(settings["climate_entity"])
                changed = getattr(
                    climate, "last_changed", source.readings["climate_entity"].reported_at
                )
                observed = coordinator.runtime.observed
                requests.append(
                    DeviceRequest(
                        member.device_id,
                        MemberPolicy.from_settings(settings),
                        member.priority,
                        settings["operation_mode"],
                        demand.demand,
                        source.running,
                        source.climate_valid,
                        source.energy.schedule_allowed,
                        source.energy.temperature_valid,
                        measured_watts=source.values["ac_power"],
                        power_reported_at=power.reported_at.timestamp()
                        if power.reported_at
                        else None,
                        state_reported_at=changed.timestamp() if changed else None,
                        last_start=observed.last_start
                        if observed.running == source.running
                        else now.timestamp(),
                        last_stop=observed.last_stop
                        if observed.running == source.running
                        else now.timestamp(),
                    )
                )
            assert captured is not None
            load = captured.readings["load_power_entity"].reported_at
            grid = captured.readings["grid_power_entity"].reported_at
            snapshot = GroupSnapshot(
                group.group_id,
                now.timestamp(),
                captured.energy,
                tuple(requests),
                load.timestamp() if load else None,
                grid.timestamp() if grid else None,
            )
            result = allocate(snapshot, previous, group.policy, shadow=True)
            self.states[group.group_id] = replace(result.state, reservations=previous.reservations)
            results[group.group_id] = {
                "shadow": True,
                "reason": result.reason,
                "available_watts": result.available_watts,
                "unresolved_reserved_watts": result.reserved_watts,
                "shadow_reserved_watts": result.shadow_reserved_watts,
                "unmet_deficit_watts": result.unmet_deficit_watts,
                "decisions": [asdict(d) for d in result.decisions],
            }
        self.results = results
        active_groups = {g.group_id for g in registry.groups}
        self.states = {key: state for key, state in self.states.items() if key in active_groups}
        self.configs = {key: config for key, config in self.configs.items() if key in active_groups}

    def diagnostics(self, device_id: str) -> dict[str, Any] | None:
        if self.error:
            return {"shadow": True, "reason": self.error}
        registry = self.repository.registry
        member = registry.membership(device_id) if registry else None
        if member is None:
            return None
        return self.results.get(member.group_id, {"shadow": True, "reason": "missing_group"})


def get_group_observer(hass: Any) -> GroupObserver:
    key = "solar_climate_manager.group_observer"
    if key not in hass.data:
        hass.data[key] = GroupObserver(hass)
    observer: GroupObserver = hass.data[key]
    return observer
