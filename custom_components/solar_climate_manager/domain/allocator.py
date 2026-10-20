"""Atomic, deterministic group allocation. No HA imports or command side effects."""

from dataclasses import dataclass, replace
from math import isfinite
from typing import Literal

from .groups import GroupPolicy, MemberPolicy
from .types import Action, EnergySnapshot


@dataclass(frozen=True)
class DeviceRequest:
    device_id: str
    policy: MemberPolicy = MemberPolicy()
    priority: int = 0  # Larger values win; device_id breaks ties.
    operation_mode: str = "control"
    demand: bool = True
    running: bool | None = False
    available: bool = True
    schedule_allowed: bool = True
    temperature_valid: bool = True
    measured_watts: float | None = None
    power_reported_at: float | None = None
    state_reported_at: float | None = None
    last_start: float | None = None
    last_stop: float | None = None
    state_observed_at: float | None = None
    command_confirmed_at: float | None = None

    def __post_init__(self) -> None:
        if not self.device_id or self.operation_mode not in (
            "control",
            "observation",
            "disabled",
            "temporary_block",
        ):
            raise ValueError("invalid_device_request")
        if type(self.priority) is not int or self.priority < 0:
            raise ValueError("invalid_priority")

    @property
    def watts(self) -> float | None:
        if self.policy.power_accounting == "estimated":
            return self.policy.planned_watts if self.running else (None if self.running is None else 0.0)
        if self.measured_watts is not None:
            return (
                self.measured_watts
                if not isinstance(self.measured_watts, bool)
                and isfinite(self.measured_watts)
                and self.measured_watts >= 0
                else None
            )
        if self.policy.ac_power_entity or self.running is None:
            return None
        return self.policy.estimated_ac_power if self.running else 0.0


@dataclass(frozen=True)
class GroupSnapshot:
    group_id: str
    now: float
    energy: EnergySnapshot
    requests: tuple[DeviceRequest, ...]
    load_reported_at: float | None = None
    grid_reported_at: float | None = None
    complete: bool = True


@dataclass(frozen=True)
class Reservation:
    device_id: str
    watts: float  # Additional draw beyond baseline device consumption.
    created_at: float
    baseline_watts: float = 0
    phase: Literal["reserved", "command_pending", "uncertain", "accounted"] = "reserved"
    sent_at: float | None = None
    stop_sent_at: float | None = None
    shadow: bool = False

    def __post_init__(self) -> None:
        if not self.device_id or self.phase not in (
            "reserved",
            "command_pending",
            "uncertain",
            "accounted",
        ):
            raise ValueError("invalid_reservation")
        if any(
            not isfinite(value) or value < 0
            for value in (self.watts, self.baseline_watts, self.created_at)
        ):
            raise ValueError("invalid_reservation")


@dataclass(frozen=True)
class AllocationState:
    group_id: str
    reservations: tuple[Reservation, ...] = ()
    soc_blocked: bool = False
    deficit_since: float | None = None
    grid_absent_since: float | None = None
    confirmations: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True)
class DeviceAllocation:
    device_id: str
    action: Action
    reason: str
    reserved_watts: float = 0


@dataclass(frozen=True)
class GroupAllocation:
    state: AllocationState
    decisions: tuple[DeviceAllocation, ...]
    available_watts: float | None
    reserved_watts: float
    shadow_reserved_watts: float
    unmet_deficit_watts: float
    reason: str
    shadow: bool


def command_dispatched(state: AllocationState, device_id: str, now: float) -> AllocationState:
    """Future executor must commit this transition before awaiting the service."""
    reservation = next((r for r in state.reservations if r.device_id == device_id), None)
    if reservation is None or reservation.phase != "reserved" or reservation.shadow:
        raise ValueError("no_real_reservation")
    if not isfinite(now) or now < reservation.created_at:
        raise ValueError("invalid_dispatch_time")
    return replace(
        state,
        reservations=tuple(
            replace(r, phase="command_pending", sent_at=now) if r is reservation else r
            for r in state.reservations
        ),
    )


def command_completed(
    state: AllocationState, device_id: str, *, failed: bool = False
) -> AllocationState:
    """Service return never releases power; failure/cancellation remains uncertain."""
    return replace(
        state,
        reservations=tuple(
            replace(r, phase="uncertain")
            if r.device_id == device_id and failed and r.phase == "command_pending"
            else r
            for r in state.reservations
        ),
    )


def stop_dispatched(state: AllocationState, device_id: str, now: float) -> AllocationState:
    return replace(
        state,
        reservations=tuple(
            replace(r, stop_sent_at=now) if r.device_id == device_id else r
            for r in state.reservations
        ),
    )


def revoke_unsent(state: AllocationState, device_id: str) -> AllocationState:
    """Only a reservation which was never dispatched can be safely revoked."""
    return replace(
        state,
        reservations=tuple(
            r
            for r in state.reservations
            if not (r.device_id == device_id and r.phase == "reserved")
        ),
    )


def _after(value: float | None, since: float, now: float) -> bool:
    return value is not None and isfinite(value) and since < value <= now


def _covered(
    snapshot: GroupSnapshot, request: DeviceRequest, since: float, policy: GroupPolicy
) -> bool:
    if (
        not snapshot.complete
        or snapshot.energy.grid is None
        or not _valid(snapshot.energy.load)
        or not _valid(snapshot.energy.battery, signed=True)
    ):
        return False
    assert snapshot.energy.load is not None and snapshot.energy.battery is not None
    load = snapshot.energy.load - (
        max(0, -snapshot.energy.battery) if policy.load_includes_battery_charging else 0
    )
    if (
        load < 0
        or policy.load_scope == "includes_all_members"
        and (
            any(r.watts is None for r in snapshot.requests)
            or sum(
                r.watts or 0 for r in snapshot.requests
                if r.policy.power_accounting != "estimated"
            ) > load
        )
    ):
        return False
    if (
        snapshot.energy.grid
        and snapshot.energy.grid_limit_configured
        and snapshot.energy.grid_import_limit != 0
        and not _valid(snapshot.energy.grid_power, signed=True)
    ):
        return False
    if not _telemetry_ready(snapshot, policy):
        return False
    if request.policy.power_accounting == "estimated":
        # Aggregate reports prove current group load, not individual consumption.
        # Require reports captured after the complete stabilization interval.
        return _after(snapshot.load_reported_at, since, snapshot.now) and (
            not snapshot.energy.grid
            or not snapshot.energy.grid_limit_configured
            or snapshot.energy.grid_import_limit == 0
            or _after(snapshot.grid_reported_at, since, snapshot.now)
        )
    if not _after(request.power_reported_at, since, snapshot.now):
        return False
    assert request.power_reported_at is not None
    if not _after(snapshot.load_reported_at, since, snapshot.now):
        return False
    assert snapshot.load_reported_at is not None
    if (
        policy.load_scope == "includes_all_members"
        and snapshot.load_reported_at < request.power_reported_at
    ):
        return False
    if (
        snapshot.energy.grid
        and snapshot.energy.grid_limit_configured
        and snapshot.energy.grid_import_limit != 0
    ):
        if not _after(snapshot.grid_reported_at, since, snapshot.now):
            return False
        assert snapshot.grid_reported_at is not None
        if snapshot.grid_reported_at < request.power_reported_at:
            return False
    return True


def reconcile(
    snapshot: GroupSnapshot, state: AllocationState, policy: GroupPolicy
) -> tuple[AllocationState, float, float]:
    """Charge only unaccounted incremental power; stale aggregates prove nothing."""
    requests = {r.device_id: r for r in snapshot.requests}
    updated = []
    pending = shadow_pending = 0.0
    for reserve in state.reservations:
        request = requests.get(reserve.device_id)
        if reserve.phase == "accounted":
            updated.append(reserve)
            continue
        remainder = reserve.watts
        if request and request.available and request.policy.power_accounting == "estimated":
            observed = request.state_observed_at or request.state_reported_at
            if (
                reserve.stop_sent_at is not None
                and request.running is False
                and _after(observed, reserve.stop_sent_at, snapshot.now)
                and _covered(
                    snapshot, request,
                    reserve.stop_sent_at + request.policy.power_settle_seconds, policy,
                )
                and snapshot.load_reported_at is not None
                and snapshot.load_reported_at >= (observed or 0)
            ):
                continue
            confirmed = request.command_confirmed_at
            if (
                reserve.phase == "command_pending"
                and reserve.stop_sent_at is None
                and reserve.sent_at is not None
                and request.running is True
                and _after(confirmed, reserve.sent_at, snapshot.now)
                and _covered(
                    snapshot, request,
                    (confirmed or 0) + request.policy.power_settle_seconds, policy,
                )
            ):
                reserve = replace(reserve, phase="accounted")
                remainder = 0.0
        if (
            request
            and request.available
            and request.policy.power_accounting != "estimated"
            and request.measured_watts is not None
            and request.watts is not None
        ):
            # An off report alone may predate an in-flight start; require a later
            # explicit stop and a coherent meter/aggregate report before release.
            if (
                reserve.stop_sent_at is not None
                and request.running is False
                and (
                    _after(request.state_observed_at or request.state_reported_at, reserve.stop_sent_at, snapshot.now)
                    and _covered(snapshot, request, reserve.stop_sent_at, policy)
                    and request.measured_watts <= reserve.baseline_watts
                )
            ):
                continue
            if (
                reserve.sent_at is not None
                and request.running is True
                and (
                    _after(request.state_observed_at or request.state_reported_at, reserve.sent_at, snapshot.now)
                    and _covered(snapshot, request, reserve.sent_at, policy)
                )
            ):
                remainder = max(
                    0.0, reserve.watts - max(0.0, request.measured_watts - reserve.baseline_watts)
                )
                if remainder == 0:
                    reserve = replace(reserve, phase="accounted")
        if reserve.shadow:
            shadow_pending += remainder
        else:
            pending += remainder
        updated.append(reserve)
    return replace(state, reservations=tuple(updated)), pending, shadow_pending


def member_load(snapshot: GroupSnapshot, state: AllocationState) -> float:
    """Excluded members: a pending estimate is already charged by its reservation."""
    pending = {r.device_id: r for r in state.reservations if r.phase != "accounted"}
    return sum(
        pending[r.device_id].baseline_watts
        if r.policy.power_accounting == "estimated" and r.device_id in pending
        else r.watts or 0.0
        for r in snapshot.requests
    )


def _valid(value: float | None, *, signed: bool = False) -> bool:
    return (
        value is not None
        and not isinstance(value, bool)
        and isfinite(value)
        and (signed or value >= 0)
    )


def _telemetry_ready(snapshot: GroupSnapshot, policy: GroupPolicy) -> bool:
    """A member's new consumption cannot be hidden behind an older aggregate."""
    load_time = snapshot.load_reported_at
    if (
        load_time is None
        or not isfinite(load_time)
        or not 0 <= snapshot.now - load_time <= policy.power_max_data_age
    ):
        return False
    limited = (
        snapshot.energy.grid is True
        and snapshot.energy.grid_limit_configured
        and snapshot.energy.grid_import_limit != 0
    )
    grid_time = snapshot.grid_reported_at
    if limited and (
        grid_time is None
        or not isfinite(grid_time)
        or not 0 <= snapshot.now - grid_time <= policy.power_max_data_age
    ):
        return False
    for request in snapshot.requests:
        report = request.state_reported_at
        if request.running and request.policy.power_accounting == "estimated" and (
            report is None or load_time <= report + request.policy.power_settle_seconds
            or limited and grid_time is not None and grid_time <= report + request.policy.power_settle_seconds
        ):
            return False
        if request.running and (
            report is None
            or not isfinite(report)
            or report > load_time
            or limited
            and grid_time is not None
            and report > grid_time
        ):
            return False
        if request.measured_watts is not None and request.policy.power_accounting != "estimated":
            power_time = request.power_reported_at
            if (
                power_time is None
                or not isfinite(power_time)
                or not 0 <= snapshot.now - power_time <= policy.power_max_data_age
            ):
                return False
            if policy.load_scope == "includes_all_members" and power_time > load_time:
                return False
            if limited and grid_time is not None and power_time > grid_time:
                return False
    return True


def allocate(
    snapshot: GroupSnapshot, state: AllocationState, policy: GroupPolicy, *, shadow: bool = True
) -> GroupAllocation:
    """One immutable next state for all requests: no competing read/modify/write grants."""
    if snapshot.group_id != state.group_id:
        raise ValueError("group_mismatch")
    if len({r.device_id for r in snapshot.requests}) != len(snapshot.requests):
        raise ValueError("duplicate_device")
    if len({r.device_id for r in state.reservations}) != len(state.reservations):
        raise ValueError("duplicate_reservation")
    if not shadow and any(r.shadow for r in state.reservations):
        raise ValueError("shadow_reservation_in_real_budget")
    if not isfinite(snapshot.now):
        raise ValueError("invalid_time")
    now, energy = snapshot.now, snapshot.energy
    state, real_pending, shadow_pending = reconcile(snapshot, state, policy)
    pending = real_pending + shadow_pending
    blocked = state.soc_blocked
    if _valid(energy.soc) and energy.soc is not None and energy.soc <= 100:
        if energy.soc < policy.minimum_soc:
            blocked = True
        elif energy.soc >= policy.restart_soc:
            blocked = False
    outage_since = (
        None
        if energy.grid is not False
        else (state.grid_absent_since if state.grid_absent_since is not None else now)
    )
    reason = "grid_ready" if energy.grid else "solar_ready"
    hard = False
    budget: float | None = None
    if (
        not _valid(energy.soc)
        or energy.soc is None
        or energy.soc > 100
        or not _valid(energy.battery, signed=True)
        or energy.grid is None
    ):
        reason, hard = "invalid_energy_data", True
    elif energy.grid is False and (
        blocked or energy.soc < policy.restart_soc and not any(r.running for r in snapshot.requests)
    ):
        blocked = True
        reason, hard = "low_soc" if energy.soc < policy.minimum_soc else "soc_recovery", True
    elif (
        energy.grid
        and blocked
        and energy.battery is not None
        and energy.battery > policy.max_battery_discharge
    ):
        reason, hard = "battery_discharge", True
    elif not snapshot.complete or any(
        not r.available or r.running is None or r.watts is None for r in snapshot.requests
    ):
        reason = "incomplete_members"
    elif not _valid(energy.load):
        reason = "invalid_load"
    else:
        assert energy.load is not None and energy.battery is not None
        load = energy.load - (
            max(0, -energy.battery) if policy.load_includes_battery_charging else 0
        )
        measured = sum(r.watts or 0 for r in snapshot.requests if r.policy.power_accounting != "estimated")
        if load < 0 or policy.load_scope == "includes_all_members" and measured > load:
            reason = "inconsistent_load"
        else:
            total = load if policy.load_scope == "includes_all_members" else load + member_load(snapshot, state)
            if energy.grid:
                if energy.grid_limit_configured and energy.grid_import_limit != 0:
                    if not _valid(energy.grid_import_limit):
                        reason, hard = "grid_limit_unavailable", True
                    elif not _valid(energy.grid_power, signed=True):
                        reason, hard = "grid_power_unavailable", True
                    else:
                        assert (
                            energy.grid_import_limit is not None and energy.grid_power is not None
                        )
                        budget = energy.grid_import_limit - energy.grid_power - pending
                else:
                    # Unlimited by policy, not a claim about physical supply capacity.
                    budget = sum(r.policy.planned_watts for r in snapshot.requests) - pending
            elif _valid(energy.pv):
                assert energy.pv is not None
                budget = energy.pv - total - pending
            else:
                reason, hard = "invalid_solar_data", True
    if budget is not None and budget < 0:
        reason = "grid_import_limit" if energy.grid else "outage_deficit"
    deficit_since = (
        now
        if budget is not None and budget < 0 and state.deficit_since is None
        else state.deficit_since
    )
    if budget is None or budget >= 0:
        deficit_since = None
    state = replace(
        state, soc_blocked=blocked, grid_absent_since=outage_since, deficit_since=deficit_since
    )
    deficit = max(0.0, -(budget or 0))
    decisions: dict[str, DeviceAllocation] = {}

    def controllable(r: DeviceRequest) -> bool:
        return r.operation_mode == "control" or shadow and r.operation_mode == "observation"

    candidates = []
    for request in snapshot.requests:
        if not controllable(request):
            decisions[request.device_id] = DeviceAllocation(
                request.device_id, "wait", request.operation_mode
            )
        elif request.running:
            run_ready = (
                request.last_start is not None
                and now - request.last_start >= request.policy.minimum_run_time
            )
            if (
                hard
                or not request.temperature_valid
                or not request.schedule_allowed
                or not request.demand
                and run_ready
            ):
                why = (
                    reason
                    if hard
                    else "invalid_temperature"
                    if not request.temperature_valid
                    else "outside_schedule"
                    if not request.schedule_allowed
                    else "no_temperature_demand"
                )
                decisions[request.device_id] = DeviceAllocation(request.device_id, "stop", why)
                deficit = max(0.0, deficit - (request.watts or 0))
            else:
                decisions[request.device_id] = DeviceAllocation(
                    request.device_id,
                    "continue",
                    "minimum_run" if not request.demand else "running",
                )
                candidates.append(request)
        else:
            decisions[request.device_id] = DeviceAllocation(request.device_id, "wait", reason)
    # Shed only the required prefix in ascending priority, never to promote a waiting device.
    grid_deficit = energy.grid is True and deficit > 0
    sustained = deficit_since is not None and now - deficit_since >= policy.shortage_delay
    for request in sorted(candidates, key=lambda r: (r.priority, -(r.watts or 0), r.device_id)):
        if deficit <= 0:
            break
        min_run_done = (
            request.last_start is not None
            and now - request.last_start >= request.policy.minimum_run_time
        )
        outage_expired = (
            outage_since is not None and now - outage_since >= policy.grid_absence_delay
        )
        if grid_deficit or sustained and (min_run_done or outage_expired):
            decisions[request.device_id] = DeviceAllocation(
                request.device_id, "stop", "grid_import_limit" if grid_deficit else "outage_deficit"
            )
            deficit = max(0.0, deficit - (request.watts or 0))
    # Stop proposals do not free measured power in this cycle.
    available = max(0.0, budget) if budget is not None else None
    # Forecasts guide new starts, never confirm physical commands or invent
    # present capacity. Account for a predicted PV drop over the whole horizon.
    forecast_available = available
    if (
        available is not None
        and _valid(energy.pv)
        and energy.forecasts
        and all(_valid(value) for value in energy.forecasts)
        and (not energy.grid or energy.grid_limit_configured and energy.grid_import_limit != 0)
    ):
        assert energy.pv is not None
        forecast_pv = min(value for value in energy.forecasts if value is not None)
        forecast_available = max(0.0, available - max(0.0, energy.pv - forecast_pv))
    reservations = list(state.reservations)
    active = {r.device_id for r in reservations if r.phase != "accounted"}
    confirmations = dict(state.confirmations)
    next_confirmations = []
    new_reserved = 0.0
    for request in sorted(snapshot.requests, key=lambda r: (-r.priority, r.device_id)):
        if request.running or not controllable(request):
            continue
        why = reason
        if not request.available or request.running is None:
            why = "device_unavailable"
        elif not request.demand:
            why = "no_temperature_demand"
        elif not request.temperature_valid or not request.schedule_allowed:
            why = "invalid_temperature" if not request.temperature_valid else "outside_schedule"
        elif request.device_id in active:
            why = "command_unconfirmed"
        elif any(r.phase == "uncertain" for r in reservations):
            why = "unresolved_reservation"
        elif hard or available is None:
            pass
        else:
            incremental = max(0.0, request.policy.planned_watts - (request.watts or 0))
            # Never trust a pre-start aggregate for manually started members either.
            coherent = _telemetry_ready(snapshot, policy)
            if not coherent:
                why = "telemetry_unsettled"
            elif incremental > available:
                why = "insufficient_budget"
            elif forecast_available is not None and incremental > forecast_available:
                why = "forecast_deficit"
            else:
                since = confirmations.get(request.device_id, now)
                next_confirmations.append((request.device_id, since))
                off_left = (
                    max(0, request.policy.minimum_off_time - (now - request.last_stop))
                    if request.last_stop is not None
                    else 0
                )
                confirmation_left = (
                    max(0, policy.start_delay - (now - since)) if not energy.grid else 0
                )
                if off_left or confirmation_left:
                    why = "minimum_off" if off_left >= confirmation_left else "start_confirmation"
                else:
                    available -= incremental
                    if forecast_available is not None:
                        forecast_available -= incremental
                    new_reserved += incremental
                    # Replace an old accounted cycle only when a fresh start is proposed.
                    reservations = [r for r in reservations if r.device_id != request.device_id]
                    reservations.append(
                        Reservation(
                            request.device_id,
                            incremental,
                            now,
                            baseline_watts=request.watts or 0,
                            shadow=shadow,
                        )
                    )
                    decisions[request.device_id] = DeviceAllocation(
                        request.device_id, "start", reason, incremental
                    )
                    continue
        decisions[request.device_id] = DeviceAllocation(request.device_id, "wait", why)
    next_state = replace(
        state, reservations=tuple(reservations), confirmations=tuple(next_confirmations)
    )
    return GroupAllocation(
        next_state,
        tuple(decisions[k] for k in sorted(decisions)),
        available,
        real_pending + (0 if shadow else new_reserved),
        shadow_pending + (new_reserved if shadow else 0),
        deficit,
        reason,
        shadow,
    )
