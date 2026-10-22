"""Group authority: durable admission, fresh revalidation and independent workers."""

import asyncio
import logging
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from typing import Any
from uuid import uuid4

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from ..adapters.group_sources import capture_group
from ..adapters.groups import get_group_repository
from ..adapters.learning import bind_learning, learning_view
from ..adapters.sources import read_sources
from ..domain.allocator import (
    AllocationState,
    GroupAllocation,
    GroupSnapshot,
    Reservation,
    allocate,
    reconcile,
)
from ..domain.groups import GroupConfig, GroupRegistry, MemberPolicy, UnresolvedReservation
from ..group_presentation import group_metrics
from ..manual import control_fingerprint, pause_active

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DispatchTicket:
    group_id: str
    device_id: str
    command_id: str | None
    service: str


class GroupManager:
    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self.repository = get_group_repository(hass)
        self.devices: dict[str, Any] = {}
        self.states: dict[str, AllocationState] = {}
        self.configs: dict[str, Any] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.results: dict[str, GroupAllocation] = {}
        self.snapshots: dict[str, GroupSnapshot] = {}
        self.mutating_devices: set[str] = set()
        self.issued: set[str] = set()
        self.stop_times: dict[str, float] = {}
        self.start_times: dict[str, float] = {}
        self.task: asyncio.Task[None] | None = None
        self.dirty = False
        self.error: str | None = None
        self._source_ids: frozenset[str] = frozenset()
        self._source_unsub: Any = None
        self._timer_unsub: Any = None
        self._repository_unsub: Any = None

    async def async_prepare(self, coordinator: Any) -> None:
        # Install the gate before initialize can queue a standalone command.
        coordinator.group_manager = self
        coordinator.commands.authority = self
        coordinator.commands.device_id = coordinator.device_id
        try:
            await self.repository.async_load()
        except (ValueError, OSError, HomeAssistantError):
            self.error = "group_store_unavailable"
            LOGGER.exception("Cannot establish group membership; starts are blocked")

    def register(self, coordinator: Any) -> None:
        if (
            coordinator.device_id in self.devices
            and self.devices[coordinator.device_id] is not coordinator
        ):
            raise ValueError("duplicate_device_identity")
        self.devices[coordinator.device_id] = coordinator
        if self._repository_unsub is None:
            self._repository_unsub = self.repository.subscribe(self.request_evaluation)
            self._timer_unsub = async_track_time_interval(
                self.hass, self._changed, timedelta(seconds=30)
            )
        self.request_evaluation()

    async def async_unregister(self, coordinator: Any) -> None:
        device_id = coordinator.device_id
        if self.devices.get(device_id) is coordinator:
            self.devices.pop(device_id)
        registry = self.repository.registry
        if registry:
            for reserve in registry.unresolved:
                if reserve.device_id == device_id and reserve.command_id:
                    self.issued.discard(reserve.command_id)
        self.stop_times.pop(device_id, None)
        self.start_times.pop(device_id, None)
        coordinator.group_manager = None
        if not self.devices:
            for unsubscribe in (self._source_unsub, self._timer_unsub, self._repository_unsub):
                if unsubscribe:
                    unsubscribe()
            self._source_unsub = self._timer_unsub = self._repository_unsub = None
            self._source_ids = frozenset()
            if self.task:
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass
                self.task = None
            self.states.clear()
            self.configs.clear()
            self.snapshots.clear()
            self.results.clear()
        else:
            self.request_evaluation()

    def controls(self, device_id: str) -> bool:
        registry = self.repository.registry
        # Unknown membership cannot fall back to the standalone start path.
        return (
            device_id in self.mutating_devices
            or registry is None
            or registry.membership(device_id) is not None
        )

    def has_pending(self, device_id: str) -> bool:
        registry = self.repository.registry
        return bool(registry and any(r.device_id == device_id for r in registry.unresolved))

    @callback
    def _changed(self, event: Any) -> None:
        self.request_evaluation()

    def request_evaluation(self) -> None:
        if not self.devices:
            return
        self.dirty = True
        if self.task is None:
            self.task = self.hass.async_create_task(
                self._async_run(), "solar climate groups", eager_start=False
            )

    def _subscriptions(self, registry: GroupRegistry) -> None:
        ids = frozenset(
            value for group in registry.groups for value in asdict(group.sources).values() if value
        )
        if ids != self._source_ids:
            if self._source_unsub:
                self._source_unsub()
            self._source_unsub = (
                async_track_state_change_event(self.hass, list(ids), self._changed) if ids else None
            )
            self._source_ids = ids

    def _capture(self, group: GroupConfig, registry: GroupRegistry) -> GroupSnapshot:
        cache: dict[str, Any] = {}

        def get_state(entity_id: str) -> Any:
            if entity_id not in cache:
                cache[entity_id] = self.hass.states.get(entity_id)
            return cache[entity_id]

        members = tuple(m for m in registry.memberships if m.group_id == group.group_id)
        return capture_group(
            group,
            members,
            self.devices,
            get_state,
            self.hass.config.units.temperature_unit,
            dt_util.utcnow(),
            dt_util.now().date(),
        )

    def _state(
        self, group: GroupConfig, registry: GroupRegistry, *, ignore: str | None = None
    ) -> AllocationState:
        members = tuple(m for m in registry.memberships if m.group_id == group.group_id)
        signature = (group, members)
        previous = self.states.get(group.group_id, AllocationState(group.group_id))
        if self.configs.get(group.group_id) != signature:
            previous = AllocationState(group.group_id, soc_blocked=previous.soc_blocked)
        self.configs[group.group_id] = signature
        return replace(
            previous,
            reservations=tuple(
                Reservation(
                    r.device_id,
                    r.watts,
                    r.created_at,
                    r.baseline_watts,
                    phase=r.phase if r.command_id in self.issued else "uncertain",
                    sent_at=self.start_times.get(r.device_id, r.sent_at),
                    stop_sent_at=self.stop_times.get(r.device_id),
                )
                for r in registry.unresolved
                if r.group_id == group.group_id
                and not (ignore is not None and r.command_id == ignore)
            ),
        )

    def _compute(
        self, group: GroupConfig, registry: GroupRegistry, *, ignore: str | None = None
    ) -> tuple[GroupSnapshot, GroupAllocation]:
        snapshot = self._capture(group, registry)
        previous = self._state(group, registry, ignore=ignore)
        result = allocate(snapshot, previous, group.policy, shadow=False)
        # Proposals are not commitments until async_authorize saves one.
        self.states[group.group_id] = replace(result.state, reservations=previous.reservations)
        self.results[group.group_id] = result
        self.snapshots[group.group_id] = snapshot
        return snapshot, result

    def _desired(
        self,
        device_id: str,
        snapshot: GroupSnapshot,
        result: GroupAllocation,
        registry: GroupRegistry,
        *,
        ignore: str | None = None,
    ) -> bool | None:
        request = next((r for r in snapshot.requests if r.device_id == device_id), None)
        if request is None or request.operation_mode != "control" or not request.available:
            return None
        decision = next(d for d in result.decisions if d.device_id == device_id)
        pending = [
            r
            for r in registry.unresolved
            if r.group_id == snapshot.group_id
            and not (ignore is not None and r.command_id == ignore)
        ]
        own = next((r for r in pending if r.device_id == device_id), None)
        stop_sent = self.stop_times.get(device_id)
        if (
            own is not None
            and request.policy.power_accounting == "estimated"
            and request.running is False
            and stop_sent is not None
            and request.state_observed_at is not None
            and stop_sent < request.state_observed_at <= snapshot.now
        ):
            # Repeated off commands would restart a long stabilization interval
            # forever. A fresh off waits for aggregate reconciliation instead.
            return None
        if (
            own is not None
            and request.policy.power_accounting == "estimated"
            and (
                own.phase == "uncertain"
                or own.command_id not in self.issued
                or stop_sent is not None
            )
        ):
            # An estimate cannot prove a failed or restored start. Recover through
            # an explicit off command, then fresh aggregate reports after settling.
            return False
        if (
            own is not None
            and request.running is False
            and (
                own.phase == "uncertain"
                or own.command_id not in self.issued
                or not request.demand
                or request.outdoor_block_reason is not None
                or not request.schedule_allowed
                or not request.temperature_valid
                or result.reason not in ("solar_ready", "grid_ready")
            )
        ):
            return False
        if decision.action == "start":
            # Admit the next physical start only after earlier commitments settle.
            starts = {d.device_id for d in result.decisions if d.action == "start"}
            first = min(
                (r for r in snapshot.requests if r.device_id in starts),
                key=lambda r: (-r.priority, r.device_id),
            )
            return True if not pending and first.device_id == device_id else None
        if decision.action == "continue":
            return True
        if decision.action == "stop":
            return False
        return None

    def desired(self, device_id: str) -> bool | None:
        if device_id in self.mutating_devices:
            return None
        registry = self.repository.registry
        member = registry.membership(device_id) if registry else None
        if registry is None or member is None:
            return None
        group = registry.group(member.group_id)
        if group is None:
            coordinator = self.devices.get(device_id)
            return (
                False
                if coordinator and coordinator.settings["operation_mode"] == "control"
                else None
            )
        snapshot, result = self._compute(group, registry)
        return self._desired(device_id, snapshot, result, registry)

    async def _settle(self, group: GroupConfig) -> None:
        registry = self.repository.registry
        if registry is None:
            return
        snapshot = self._capture(group, registry)
        old = self._state(group, registry)
        state, _, _ = reconcile(snapshot, old, group.policy)
        remaining = {r.device_id for r in state.reservations if r.phase != "accounted"}
        resolved = tuple(
            r
            for r in registry.unresolved
            if r.group_id == group.group_id and r.device_id not in remaining
        )
        if resolved:
            # Match entire records; a concurrent update must never erase a new command.
            await self.repository.async_update(
                lambda current: replace(
                    current, unresolved=tuple(r for r in current.unresolved if r not in resolved)
                )
            )
            for reserve in resolved:
                self.stop_times.pop(reserve.device_id, None)
                self.start_times.pop(reserve.device_id, None)
                if reserve.command_id:
                    self.issued.discard(reserve.command_id)

    async def _async_run(self) -> None:
        try:
            while self.dirty:
                self.dirty = False
                registry = self.repository.registry
                if registry is None:
                    return
                self.error = None
                self._subscriptions(registry)
                for group in registry.groups:
                    lock = self.locks.setdefault(group.group_id, asyncio.Lock())
                    async with lock:
                        try:
                            await self._settle(group)
                            current = self.repository.registry
                            assert current is not None
                            actual = current.group(group.group_id)
                            if actual is not None:
                                self._observe_learning(actual, current)
                                self._compute(actual, current)
                        except (ValueError, OSError, HomeAssistantError):
                            self.error = "group_storage_error"
                            LOGGER.exception("Group evaluation or persistence failed")
                observers = {
                    c.group_observer for c in self.devices.values() if c.group_observer is not None
                }
                for observer in observers:
                    observer.evaluate()
                for coordinator in tuple(self.devices.values()):
                    if coordinator.data and not coordinator.commands.closed:
                        coordinator.async_set_updated_data(
                            {**coordinator.data, **self.public_state(coordinator)}
                        )
                        coordinator.commands.schedule()
        finally:
            self.task = None

    def _observe_learning(self, group: GroupConfig, registry: GroupRegistry) -> None:
        snapshot = self._capture(group, registry)
        members = tuple(m for m in registry.memberships if m.group_id == group.group_id)
        load = snapshot.energy.load
        battery_valid = True
        if group.policy.load_includes_battery_charging:
            battery = self.hass.states.get(group.sources.battery_power_entity)
            stamp = battery.last_reported.timestamp() if battery else None
            battery_valid = bool(stamp is not None and snapshot.load_reported_at is not None
                                 and 0 <= snapshot.now - stamp <= 90
                                 and abs(stamp - snapshot.load_reported_at) <= 30
                                 and snapshot.energy.battery is not None)
            if battery_valid and load is not None:
                load -= max(0, -(snapshot.energy.battery or 0))
        for request in snapshot.requests:
            coordinator = self.devices.get(request.device_id)
            if coordinator is None or not hasattr(coordinator, "power_learning"):
                continue
            before = coordinator.power_learning.stored()
            learning = bind_learning(coordinator, group, members)
            settings = coordinator.settings
            eligible = bool(
                settings.get("power_learning_enabled")
                and request.policy.power_accounting == "estimated"
                and group.policy.load_scope == "includes_all_members"
                and snapshot.complete and battery_valid and request.operation_mode == "control"
                and all(r.running is False for r in snapshot.requests if r.device_id != request.device_id)
                and not any(r.group_id == group.group_id and (
                    r.device_id != request.device_id or r.command_id not in self.issued
                ) for r in registry.unresolved)
                and coordinator.commands.state.error == "none"
            )
            climate = self.hass.states.get(settings["climate_entity"])
            cycle_key = repr(control_fingerprint(climate.state, climate.attributes)) if climate else ""
            learning.observe(
                now=snapshot.now, reported=snapshot.load_reported_at, watts=load,
                running=request.running, changed=request.state_reported_at,
                confirmed=request.command_confirmed_at, eligible=eligible,
                settle=request.policy.power_settle_seconds, cycle_key=cycle_key,
            )
            if before != learning.stored():
                coordinator.store.async_delay_save(coordinator._stored_state, 1)

    def _command_matches(
        self, coordinator: Any, desired: bool | None, service: str, payload: dict[str, Any]
    ) -> bool:
        if (
            desired is None
            or coordinator.commands.closed
            or coordinator.settings["operation_mode"] != "control"
        ):
            return False
        if pause_active(coordinator.runtime.manual_date, dt_util.now().date()):
            return False
        if (service == "set_temperature") != desired:
            return False
        # Rebuild the command with current target/temperature/device state, never
        # accept a payload built before an awaited storage write changed the world.
        climate = self.hass.states.get(coordinator.settings["climate_entity"])
        if climate is None or climate.state in ("unknown", "unavailable"):
            return False
        source = read_sources(
            self.hass.states.get,
            coordinator.settings,
            coordinator.runtime.device,
            self.hass.config.units.temperature_unit,
            dt_util.utcnow(),
            last_temperature=coordinator.last_temperature,
        )
        data = {"temperature": source.temperature, "ac_temperature": source.ac_temperature}
        return bool(coordinator.commands._control_command(climate, data) == (service, payload))

    async def async_authorize(
        self, device_id: str, service: str, payload: dict[str, Any], expected_climate: Any
    ) -> DispatchTicket | None:
        if device_id in self.mutating_devices:
            return None
        registry = self.repository.registry
        member = registry.membership(device_id) if registry else None
        if registry is None or member is None:
            return None
        group_id = member.group_id
        async with self.locks.setdefault(group_id, asyncio.Lock()):
            registry = self.repository.registry
            assert registry is not None
            if registry.membership(device_id) != member:
                return None
            group = registry.group(group_id)
            coordinator = self.devices.get(device_id)
            if coordinator is None:
                return None
            if group is None:
                if self._command_matches(coordinator, False, service, payload):
                    return DispatchTicket(group_id, device_id, None, service)
                return None
            try:
                await self._settle(group)
            except (ValueError, OSError, HomeAssistantError):
                self.error = "group_storage_error"
                if service != "set_hvac_mode":
                    raise
                LOGGER.exception("Cannot settle group storage; protective stop remains allowed")
            registry = self.repository.registry
            assert registry is not None
            snapshot, result = self._compute(group, registry)
            desired = self._desired(device_id, snapshot, result, registry)
            if not self._command_matches(coordinator, desired, service, payload):
                return None
            request = next(r for r in snapshot.requests if r.device_id == device_id)
            own = next((r for r in registry.unresolved if r.device_id == device_id), None)
            signature = (
                group,
                tuple(m for m in registry.memberships if m.group_id == group_id),
                dict(coordinator.settings),
            )
            inserted: UnresolvedReservation | None = None
            if service == "set_temperature" and request.running is False:
                reserve = next(r for r in result.state.reservations if r.device_id == device_id)
                now = dt_util.utcnow().timestamp()
                inserted = UnresolvedReservation(
                    device_id,
                    group_id,
                    reserve.watts,
                    reserve.baseline_watts,
                    now,
                    now,
                    command_id=uuid4().hex,
                    phase="command_pending",
                )
                await self.repository.async_update(
                    lambda current: replace(current, unresolved=(*current.unresolved, inserted))
                )
                own = inserted
            elif service == "set_hvac_mode" and own is not None:
                updated = replace(own, stop_sent_at=dt_util.utcnow().timestamp())
                try:
                    await self.repository.async_update(
                        lambda current: replace(
                            current,
                            unresolved=tuple(
                                updated if r == own else r for r in current.unresolved
                            ),
                        )
                    )
                except (ValueError, OSError, HomeAssistantError):
                    # Retain the full reserve; a disk failure must not prevent off.
                    self.error = "group_storage_error"
                    LOGGER.exception("Cannot persist stop timestamp; retaining group reservation")
                else:
                    own = updated
            # No await after this revalidation and before the executor starts service I/O.
            current = self.repository.registry
            assert current is not None
            actual = current.group(group_id)
            members = tuple(m for m in current.memberships if m.group_id == group_id)
            climate = self.hass.states.get(coordinator.settings["climate_entity"])
            unchanged = climate is not None and control_fingerprint(
                climate.state, climate.attributes
            ) == control_fingerprint(expected_climate.state, expected_climate.attributes)
            valid = (
                device_id not in self.mutating_devices
                and unchanged
                and (actual, members, dict(coordinator.settings)) == signature
            )
            if actual is not None:
                fresh, proposal = self._compute(
                    actual, current, ignore=inserted.command_id if inserted else None
                )
                desired = self._desired(
                    device_id,
                    fresh,
                    proposal,
                    current,
                    ignore=inserted.command_id if inserted else None,
                )
                valid = valid and self._command_matches(coordinator, desired, service, payload)
            else:
                valid = False
            if not valid:
                if inserted is not None:
                    await self.repository.async_update(
                        lambda state: replace(
                            state, unresolved=tuple(r for r in state.unresolved if r != inserted)
                        )
                    )
                return None
            if service == "set_hvac_mode" and own is not None:
                # The write-ahead timestamp predates awaited I/O. Only reports
                # after actual dispatch can prove off; reload requires a new stop.
                self.stop_times[device_id] = dt_util.utcnow().timestamp()
            if own and own.command_id:
                self.issued.add(own.command_id)
            if inserted is not None:
                self.start_times[device_id] = dt_util.utcnow().timestamp()
            return DispatchTicket(group_id, device_id, own.command_id if own else None, service)

    async def async_finished(self, ticket: DispatchTicket, *, failed: bool) -> None:
        if failed and ticket.command_id is not None:
            try:
                await self.repository.async_update(
                    lambda state: replace(
                        state,
                        unresolved=tuple(
                            replace(r, phase="uncertain")
                            if r.command_id == ticket.command_id
                            else r
                            for r in state.unresolved
                        ),
                    )
                )
            except (ValueError, OSError, HomeAssistantError):
                self.issued.discard(ticket.command_id)
                self.error = "group_storage_error"
                LOGGER.exception("Unable to persist uncertain group command")
        self.request_evaluation()

    def public_state(self, coordinator: Any) -> dict[str, Any]:
        device_id = coordinator.device_id
        registry = self.repository.registry
        member = registry.membership(device_id) if registry else None
        data: dict[str, Any] = {
            "group_name": None,
            "group_available_power": None,
            "group_load_power": None,
            "group_reserved_power": None,
            "group_action": "independent",
            "group_reason": "independent",
            "group_command_status": "idle",
        }
        if hasattr(coordinator, "power_learning"):
            data["power_learning"] = learning_view(coordinator, dt_util.utcnow().timestamp())
        if registry is None:
            data.update(group_action="wait", group_reason="group_store_unavailable")
            return data
        if member is None:
            if device_id in self.mutating_devices:
                data.update(group_action="wait", group_reason="group_not_ready")
            return data
        group = registry.group(member.group_id)
        data.update(
            group_action="wait",
            group_reason="missing_group" if group is None else "group_not_ready",
        )
        if group is None:
            return data
        data["group_name"] = group.name[:255]
        policy = MemberPolicy.from_settings(coordinator.settings)
        data["effective_power_accounting"] = policy.power_accounting
        result = self.results.get(group.group_id)
        snapshot = self.snapshots.get(group.group_id)
        if result is not None and snapshot is not None:
            data.update(group_metrics(snapshot, result, group.policy))
            decision = next((d for d in result.decisions if d.device_id == device_id), None)
            if decision:
                data.update(group_action=decision.action, group_reason=decision.reason)
                desired = self._desired(device_id, snapshot, result, registry)
                if decision.action == "start" and desired is None:
                    data.update(
                        group_action="wait",
                        group_reason="awaiting_previous_start"
                        if any(r.group_id == group.group_id for r in registry.unresolved)
                        else "higher_priority",
                    )
                elif desired is False and decision.action != "stop":
                    data.update(group_action="stop", group_reason="recovering_command")
                if coordinator.settings["operation_mode"] == "observation":
                    observer = coordinator.group_observer
                    preview = observer.diagnostics(device_id) if observer else None
                    proposed = next(
                        (
                            d
                            for d in (preview or {}).get("decisions", [])
                            if d["device_id"] == device_id
                        ),
                        None,
                    )
                    if proposed:
                        data.update(
                            group_action="preview_" + proposed["action"],
                            group_reason=proposed["reason"],
                        )
        reserve = next((r for r in registry.unresolved if r.device_id == device_id), None)
        attempt = coordinator.commands.state.attempt
        if reserve:
            data["group_command_status"] = (
                "awaiting_stop"
                if device_id in self.stop_times
                else "uncertain"
                if reserve.phase == "uncertain" or reserve.command_id not in self.issued
                else "service_pending"
                if attempt and attempt.service_status == "pending"
                else ("awaiting_stabilization" if policy.power_accounting == "estimated" else "awaiting_meter")
                if attempt and attempt.confirmed_at is not None
                else "awaiting_confirmation"
            )
        elif attempt:
            data["group_command_status"] = (
                "confirmed"
                if attempt.confirmed_at is not None
                else "service_pending"
                if attempt.service_status == "pending"
                else "failed"
                if attempt.service_status in ("failed", "cancelled")
                else "awaiting_confirmation"
            )
        if device_id in self.mutating_devices:
            data.update(group_action="wait", group_reason="group_not_ready")
        if self.error:
            data["group_reason"] = self.error
        return data

    def diagnostics(self, device_id: str) -> dict[str, Any] | None:
        registry = self.repository.registry
        member = registry.membership(device_id) if registry else None
        if registry is None:
            return {"reason": "group_store_unavailable", "starts_blocked": True}
        if member is None:
            return None
        result = self.results.get(member.group_id)
        return {
            "shadow": False,
            "public_state": {
                k: v
                for k, v in self.public_state(self.devices[device_id]).items()
                if k != "group_name"
            }
            if device_id in self.devices
            else None,
            "reason": self.error or (result.reason if result else "group_not_ready"),
            "reservations": [
                asdict(r) for r in registry.unresolved if r.group_id == member.group_id
            ],
            "decisions": [asdict(d) for d in result.decisions] if result else [],
            "awaiting_confirmation": any(
                r.group_id == member.group_id for r in registry.unresolved
            ),
        }


def get_group_manager(hass: Any) -> GroupManager:
    key = "solar_climate_manager.group_manager"
    if key not in hass.data:
        hass.data[key] = GroupManager(hass)
    manager: GroupManager = hass.data[key]
    return manager
