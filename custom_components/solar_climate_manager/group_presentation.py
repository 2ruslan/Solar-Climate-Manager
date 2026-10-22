"""Public group metrics; proposals never masquerade as committed reserves."""

from typing import Any

from .domain.allocator import GroupAllocation, GroupSnapshot, member_load
from .domain.groups import GroupPolicy

GROUP_REASONS = [
    "low_outdoor_temperature",
    "outdoor_temperature_unavailable",
    "independent",
    "group_not_ready",
    "group_store_unavailable",
    "group_storage_error",
    "missing_group",
    "solar_ready",
    "grid_ready",
    "invalid_energy_data",
    "low_soc",
    "soc_recovery",
    "battery_discharge",
    "incomplete_members",
    "invalid_load",
    "inconsistent_load",
    "grid_limit_unavailable",
    "grid_power_unavailable",
    "invalid_solar_data",
    "grid_import_limit",
    "outage_deficit",
    "invalid_temperature",
    "outside_schedule",
    "no_temperature_demand",
    "minimum_run",
    "temperature_maintenance",
    "running",
    "device_unavailable",
    "command_unconfirmed",
    "unresolved_reservation",
    "telemetry_unsettled",
    "insufficient_budget",
    "minimum_off",
    "start_confirmation",
    "observation",
    "disabled",
    "temporary_block",
    "awaiting_previous_start",
    "higher_priority",
    "recovering_command",
]
GROUP_ACTIONS = [
    "independent",
    "start",
    "continue",
    "stop",
    "wait",
    "preview_start",
    "preview_continue",
    "preview_stop",
    "preview_wait",
]
COMMAND_PHASES = [
    "idle",
    "service_pending",
    "awaiting_confirmation",
    "awaiting_meter",
    "awaiting_stabilization",
    "awaiting_stop",
    "uncertain",
    "confirmed",
    "failed",
]
GROUP_KEYS = (
    "group_name",
    "group_available_power",
    "group_load_power",
    "group_reserved_power",
    "group_action",
    "group_reason",
    "group_command_status",
)


def group_metrics(
    snapshot: GroupSnapshot, result: GroupAllocation, policy: GroupPolicy
) -> dict[str, Any]:
    proposals = sum(d.reserved_watts for d in result.decisions if d.action == "start")
    load = snapshot.energy.load
    battery = snapshot.energy.battery
    if load is not None and battery is not None:
        load -= max(0, -battery) if policy.load_includes_battery_charging else 0
        if policy.load_scope == "excludes_all_members":
            load = (
                load + member_load(snapshot, result.state)
                if all(r.watts is not None for r in snapshot.requests)
                else None
            )
        if load is not None and load < 0:
            load = None
    else:
        load = None
    available = result.available_watts + proposals if result.available_watts is not None else None
    if snapshot.energy.grid and (
        not snapshot.energy.grid_limit_configured or snapshot.energy.grid_import_limit == 0
    ):
        available = None  # Unlimited by policy is not measured physical headroom.
    return {
        "group_available_power": available,
        "group_load_power": load,
        "group_reserved_power": max(0.0, result.reserved_watts - proposals),
    }
