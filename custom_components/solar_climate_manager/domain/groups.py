"""Versioned group configuration; no allocation or physical command side effects."""

from dataclasses import asdict, dataclass, field, replace
from math import isfinite
from typing import Any, Literal
from uuid import uuid4

GROUP_SCHEMA_VERSION = 2
SHARED_SOURCE_KEYS = (
    "pv_power_entity",
    "load_power_entity",
    "soc_entity",
    "battery_power_entity",
    "grid_power_entity",
    "grid_import_limit_entity",
    "grid_available_entity",
    "forecast_power_now_entity",
    "forecast_power_30m_entity",
    "forecast_power_60m_entity",
)


def identifier(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invalid_identifier")
    return value


@dataclass(frozen=True)
class GroupSources:
    pv_power_entity: str | None = None
    load_power_entity: str | None = None
    soc_entity: str | None = None
    battery_power_entity: str | None = None
    grid_power_entity: str | None = None
    grid_import_limit_entity: str | None = None
    grid_available_entity: str | None = None
    forecast_power_now_entity: str | None = None
    forecast_power_30m_entity: str | None = None
    forecast_power_60m_entity: str | None = None

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            domain = (
                "number"
                if name == "grid_import_limit_entity"
                else "binary_sensor"
                if name == "grid_available_entity"
                else "sensor"
            )
            if value is not None and (
                not isinstance(value, str)
                or not value.startswith(domain + ".")
                or not value.removeprefix(domain + ".")
            ):
                raise ValueError("invalid_group_source")

    @property
    def configured(self) -> bool:
        # Static readiness only: availability, freshness and branch-specific checks
        # belong to group snapshots and allocation, not this configuration model.
        return all(
            (
                self.load_power_entity,
                self.soc_entity,
                self.battery_power_entity,
                self.grid_available_entity,
            )
        )


@dataclass(frozen=True)
class GroupPolicy:
    minimum_soc: float = 85
    restart_soc: float = 90
    max_battery_discharge: float = 100
    start_delay: float = 600
    shortage_delay: float = 600
    grid_absence_delay: float = 600
    power_max_data_age: float = 900
    grid_max_data_age: float = 86400
    load_includes_battery_charging: bool = False
    grid_on_means_available: bool = True
    battery_positive: Literal["charge", "discharge"] = "discharge"
    grid_positive: Literal["import", "export"] = "import"
    # Explicit contract: includes every member, even manually operated members.
    load_scope: Literal["includes_all_members", "excludes_all_members"] = "includes_all_members"

    def __post_init__(self) -> None:
        for name in (
            "minimum_soc",
            "restart_soc",
            "max_battery_discharge",
            "start_delay",
            "shortage_delay",
            "grid_absence_delay",
            "power_max_data_age",
            "grid_max_data_age",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError("invalid_group_policy")
        if not 0 <= self.minimum_soc < self.restart_soc <= 100:
            raise ValueError("invalid_soc_thresholds")
        if self.battery_positive not in ("charge", "discharge") or self.grid_positive not in (
            "import",
            "export",
        ):
            raise ValueError("invalid_power_sign")
        if self.load_scope not in ("includes_all_members", "excludes_all_members"):
            raise ValueError("unsupported_load_scope")
        if (
            type(self.load_includes_battery_charging) is not bool
            or type(self.grid_on_means_available) is not bool
        ):
            raise ValueError("invalid_group_flag")


@dataclass(frozen=True)
class MemberPolicy:
    """Device-specific parameters never inherited from another group member."""

    estimated_ac_power: float = 900
    minimum_run_time: float = 600
    minimum_off_time: float = 600
    ac_power_entity: str | None = None
    power_accounting: Literal["legacy", "meter", "estimated"] = "legacy"
    power_margin_percent: float = 20
    power_settle_seconds: float = 120

    def __post_init__(self) -> None:
        for value in (self.estimated_ac_power, self.minimum_run_time, self.minimum_off_time,
                      self.power_margin_percent, self.power_settle_seconds):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0
            ):
                raise ValueError("invalid_member_policy")
        if self.estimated_ac_power == 0:
            raise ValueError("invalid_member_policy")
        if self.power_accounting not in ("legacy", "meter", "estimated"):
            raise ValueError("invalid_member_policy")
        if not 0 <= self.power_margin_percent <= 100 or not 30 <= self.power_settle_seconds <= 1800:
            raise ValueError("invalid_member_policy")
        if self.power_accounting == "meter" and not self.ac_power_entity:
            raise ValueError("missing_power_meter")
        if self.ac_power_entity is not None and (
            not isinstance(self.ac_power_entity, str)
            or not self.ac_power_entity.startswith("sensor.")
            or self.ac_power_entity == "sensor."
        ):
            raise ValueError("invalid_member_source")

    @property
    def planned_watts(self) -> float:
        return self.estimated_ac_power * (
            1 + self.power_margin_percent / 100 if self.power_accounting == "estimated" else 1
        )

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "MemberPolicy":
        return cls(
            **{
                key: settings[key]
                for key in (
                    "estimated_ac_power",
                    "minimum_run_time",
                    "minimum_off_time",
                    "ac_power_entity",
                    "power_accounting",
                    "power_margin_percent",
                    "power_settle_seconds",
                )
                if key in settings
            }
        )


@dataclass(frozen=True)
class GroupConfig:
    group_id: str
    name: str
    sources: GroupSources = field(default_factory=GroupSources)
    policy: GroupPolicy = field(default_factory=GroupPolicy)

    def __post_init__(self) -> None:
        identifier(self.group_id)
        identifier(self.name)


@dataclass(frozen=True)
class Membership:
    device_id: str
    group_id: str
    priority: int = 0

    def __post_init__(self) -> None:
        identifier(self.device_id)
        identifier(self.group_id)
        if type(self.priority) is not int or self.priority < 0:
            raise ValueError("invalid_priority")


@dataclass(frozen=True)
class UnresolvedReservation:
    """Durable uncertainty; lifecycle/settlement will be implemented with allocator."""

    device_id: str
    group_id: str
    watts: float
    baseline_watts: float = 0
    created_at: float = 0
    sent_at: float | None = None
    stop_sent_at: float | None = None
    command_id: str | None = None
    phase: Literal["command_pending", "uncertain"] = "uncertain"

    def __post_init__(self) -> None:
        identifier(self.device_id)
        identifier(self.group_id)
        if (
            isinstance(self.watts, bool)
            or not isinstance(self.watts, (int, float))
            or not isfinite(self.watts)
            or self.watts < 0
        ):
            raise ValueError("invalid_reservation")
        if self.baseline_watts is None or self.created_at is None:
            raise ValueError("invalid_reservation_time_or_baseline")
        for value in (self.baseline_watts, self.created_at, self.sent_at, self.stop_sent_at):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0):
                raise ValueError("invalid_reservation_time_or_baseline")
        if self.sent_at is not None and self.sent_at < self.created_at:
            raise ValueError("invalid_dispatch_time")
        if self.phase not in ("command_pending", "uncertain"):
            raise ValueError("invalid_reservation_phase")
        if self.command_id is not None:
            identifier(self.command_id)
        if self.phase == "command_pending" and (self.sent_at is None or self.command_id is None):
            raise ValueError("missing_dispatch_identity")


@dataclass(frozen=True)
class GroupRegistry:
    groups: tuple[GroupConfig, ...] = ()
    memberships: tuple[Membership, ...] = ()
    unresolved: tuple[UnresolvedReservation, ...] = ()

    def __post_init__(self) -> None:
        if len({g.group_id for g in self.groups}) != len(self.groups):
            raise ValueError("duplicate_group")
        if len({m.device_id for m in self.memberships}) != len(self.memberships):
            raise ValueError("device_already_grouped")
        if len({r.device_id for r in self.unresolved}) != len(self.unresolved):
            raise ValueError("duplicate_reservation")
        for reserve in self.unresolved:
            member = self.membership(reserve.device_id)
            if member is not None and member.group_id != reserve.group_id:
                raise ValueError("reservation_group_mismatch")

    def membership(self, device_id: str) -> Membership | None:
        return next((m for m in self.memberships if m.device_id == device_id), None)

    def group(self, group_id: str) -> GroupConfig | None:
        return next((g for g in self.groups if g.group_id == group_id), None)

    def create(
        self, name: str, sources: GroupSources, policy: GroupPolicy
    ) -> tuple["GroupRegistry", str]:
        group = GroupConfig(uuid4().hex, name, sources, policy)
        return replace(self, groups=(*self.groups, group)), group.group_id

    def update(self, config: GroupConfig) -> "GroupRegistry":
        if self.group(config.group_id) is None:
            raise ValueError("missing_group")
        return replace(
            self, groups=tuple(config if g.group_id == config.group_id else g for g in self.groups)
        )

    def join(self, device_id: str, group_id: str, priority: int = 0) -> "GroupRegistry":
        if self.membership(device_id) is not None:
            raise ValueError("device_already_grouped")
        if any(r.device_id == device_id for r in self.unresolved):
            raise ValueError("unresolved_reservation")
        if self.group(group_id) is None:
            raise ValueError("missing_group")
        return replace(
            self, memberships=(*self.memberships, Membership(device_id, group_id, priority))
        )

    def leave(self, device_id: str) -> "GroupRegistry":
        if any(r.device_id == device_id for r in self.unresolved):
            raise ValueError("unresolved_reservation")
        return replace(
            self, memberships=tuple(m for m in self.memberships if m.device_id != device_id)
        )

    def delete(self, group_id: str) -> "GroupRegistry":
        if any(m.group_id == group_id for m in self.memberships):
            raise ValueError("group_has_members")
        if any(r.group_id == group_id for r in self.unresolved):
            raise ValueError("unresolved_reservation")
        return replace(self, groups=tuple(g for g in self.groups if g.group_id != group_id))

    def readiness(self, group_id: str, loaded_devices: frozenset[str]) -> str:
        group = self.group(group_id)
        if group is None:
            return "missing_group"
        if not group.sources.configured:
            return "incomplete_sources"
        members = {m.device_id for m in self.memberships if m.group_id == group_id}
        if not members:
            return "no_members"
        if not members <= loaded_devices:
            return "members_unavailable"
        if any(r.group_id == group_id for r in self.unresolved):
            return "unresolved_reservation"
        return "configured"  # Never a start permit; fresh budget is still required.


def serialize_registry(registry: GroupRegistry) -> dict[str, Any]:
    return {"schema_version": GROUP_SCHEMA_VERSION, **asdict(registry)}


def restore_registry(data: Any) -> GroupRegistry:
    if data is None:
        return GroupRegistry()
    if (
        not isinstance(data, dict)
        or type(data.get("schema_version")) is not int
        or data["schema_version"] not in (1, GROUP_SCHEMA_VERSION)
    ):
        raise ValueError("unsupported_group_schema")
    # Reject malformed/future data, never replace it with an empty registry.
    if set(data) != {"schema_version", "groups", "memberships", "unresolved"}:
        raise ValueError("invalid_group_schema")
    for key in ("groups", "memberships", "unresolved"):
        if not isinstance(data[key], (list, tuple)):
            raise ValueError("invalid_group_schema")
    try:
        for group in data["groups"]:
            if not isinstance(group, dict) or set(group) != {
                "group_id",
                "name",
                "sources",
                "policy",
            }:
                raise ValueError("invalid_group_schema")
        return GroupRegistry(
            groups=tuple(
                GroupConfig(
                    group_id=g["group_id"],
                    name=g["name"],
                    sources=GroupSources(**g["sources"]),
                    policy=GroupPolicy(**g["policy"]),
                )
                for g in data["groups"]
            ),
            memberships=tuple(Membership(**m) for m in data["memberships"]),
            unresolved=tuple(UnresolvedReservation(**r) for r in data["unresolved"]),
        )
    except (TypeError, KeyError) as error:
        raise ValueError("invalid_group_schema") from error
