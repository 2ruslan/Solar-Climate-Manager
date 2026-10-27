"""Read settings from their owner without merging group values into a device."""

from collections.abc import Iterator, Mapping
from dataclasses import fields
from typing import Any

from .groups import SHARED_SOURCE_KEYS, GroupConfig, GroupPolicy, MemberPolicy

GROUP_POLICY_KEYS = frozenset(field.name for field in fields(GroupPolicy))
GROUP_SETTING_KEYS = frozenset(SHARED_SOURCE_KEYS) | GROUP_POLICY_KEYS | {
    "load_includes_ac", "grid_absence_minutes",
}


class SettingsView(Mapping[str, Any]):
    """A read-only view; a missing group value never falls back to the device."""

    def __init__(
        self, device: Mapping[str, Any], group: GroupConfig | None = None,
        *, grouped: bool = False,
    ) -> None:
        self.device = device
        self.group = group
        self.grouped = grouped or group is not None

    def __getitem__(self, key: str) -> Any:
        if self.grouped:
            if key in SHARED_SOURCE_KEYS:
                return getattr(self.group.sources, key) if self.group else None
            policy = self.group.policy if self.group else GroupPolicy()
            if key in GROUP_POLICY_KEYS:
                return getattr(policy, key)
            if key == "load_includes_ac":
                return policy.load_scope == "includes_all_members"
            if key == "grid_absence_minutes":
                return policy.grid_absence_delay / 60
            if key == "ac_power_entity" and MemberPolicy.from_settings(self.device).power_accounting == "estimated":
                return None
        return self.device[key]

    def __iter__(self) -> Iterator[str]:
        return iter(dict.fromkeys((*self.device, *(GROUP_SETTING_KEYS if self.grouped else ()))))

    def __len__(self) -> int:
        return sum(1 for _ in self)


def device_values(values: Mapping[str, Any], *, grouped: bool) -> dict[str, Any]:
    """Persist only device-owned settings for group members."""
    return {key: value for key, value in values.items() if not grouped or key not in GROUP_SETTING_KEYS}
