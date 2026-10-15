"""Capture one coherent group snapshot without changing any member runtime."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from ..domain.allocator import DeviceRequest, GroupSnapshot
from ..domain.groups import GroupConfig, MemberPolicy, Membership
from ..domain.types import DeviceConfig, EnergySnapshot
from ..manual import pause_active
from ..model import evaluate
from .sources import read_sources


def capture_group(
    group: GroupConfig,
    members: tuple[Membership, ...],
    devices: dict[str, Any],
    get_state: Callable[[str], Any],
    temperature_unit: str,
    now: datetime,
    today: date,
) -> GroupSnapshot:
    requests = []
    captured = None
    for member in members:
        coordinator = devices.get(member.device_id)
        if coordinator is None or coordinator.commands.closed:
            requests.append(
                DeviceRequest(
                    member.device_id,
                    priority=member.priority,
                    available=False,
                    running=None,
                    demand=False,
                )
            )
            continue
        settings = {**coordinator.settings, **asdict(group.policy), **asdict(group.sources)}
        settings["load_includes_ac"] = group.policy.load_scope == "includes_all_members"
        source = read_sources(
            get_state,
            settings,
            DeviceConfig.from_settings(settings),
            temperature_unit,
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
        changed = getattr(climate, "last_changed", source.readings["climate_entity"].reported_at)
        observed = coordinator.runtime.observed
        requests.append(
            DeviceRequest(
                member.device_id,
                MemberPolicy.from_settings(settings),
                member.priority,
                (
                    "temporary_block"
                    if pause_active(coordinator.runtime.manual_date, today)
                    else settings["operation_mode"]
                ),
                demand.demand,
                source.running,
                source.climate_valid,
                source.energy.schedule_allowed,
                source.energy.temperature_valid,
                measured_watts=source.values["ac_power"],
                power_reported_at=power.reported_at.timestamp() if power.reported_at else None,
                state_reported_at=changed.timestamp() if changed else None,
                state_observed_at=climate.last_reported.timestamp()
                if climate is not None
                else None,
                last_start=observed.last_start
                if observed.running == source.running
                else now.timestamp(),
                last_stop=observed.last_stop
                if observed.running == source.running
                else now.timestamp(),
            )
        )
    if captured is None:
        return GroupSnapshot(
            group.group_id, now.timestamp(), EnergySnapshot(), tuple(requests), complete=False
        )
    load = captured.readings["load_power_entity"].reported_at
    grid = captured.readings["grid_power_entity"].reported_at
    return GroupSnapshot(
        group.group_id,
        now.timestamp(),
        captured.energy,
        tuple(requests),
        load.timestamp() if load else None,
        grid.timestamp() if grid else None,
        complete=all(r.available for r in requests) and group.sources.configured,
    )
