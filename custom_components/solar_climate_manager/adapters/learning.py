"""Bind learned estimates to their physical installation and current settings."""

import hashlib
import json
from dataclasses import asdict, replace
from typing import Any

from ..domain.groups import GroupConfig, MemberPolicy, Membership
from ..domain.learning import PowerLearning


def learning_context(coordinator: Any, group: GroupConfig, members: tuple[Membership, ...]) -> str:
    settings = coordinator.settings
    context = [
        asdict(group.sources),
        asdict(group.policy),
        group.group_id,
        sorted(m.device_id for m in members),
        {
            key: settings.get(key)
            for key in (
                "climate_entity",
                "hvac_mode",
                "target_temperature",
                "estimated_ac_power",
                "power_accounting",
                "power_learning_enabled",
                "power_learning_generation",
                "power_settle_seconds",
                "power_margin_percent",
            )
        },
    ]
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def bind_learning(
    coordinator: Any, group: GroupConfig, members: tuple[Membership, ...]
) -> PowerLearning:
    learning: PowerLearning = coordinator.power_learning
    learning.bind(learning_context(coordinator, group, members))
    return learning


def effective_policy(
    coordinator: Any,
    group: GroupConfig,
    members: tuple[Membership, ...],
    policy: MemberPolicy,
    now: float,
) -> MemberPolicy:
    learning = getattr(coordinator, "power_learning", None)
    if (
        learning is not None
        and coordinator.settings.get("power_learning_enabled")
        and learning.context == learning_context(coordinator, group, members)
        and policy.power_accounting == "estimated"
        and group.policy.load_scope == "includes_all_members"
    ):
        return replace(
            policy, estimated_ac_power=learning.effective(policy.estimated_ac_power, now)
        )
    return policy


def learning_view(coordinator: Any, now: float) -> dict[str, Any]:
    settings = coordinator.settings
    manager = coordinator.group_manager
    registry = manager.repository.registry if manager else None
    member = registry.membership(coordinator.device_id) if registry else None
    group = registry.group(member.group_id) if registry and member else None
    enabled = settings.get("power_learning_enabled", False)
    supported = bool(
        group
        and group.policy.load_scope == "includes_all_members"
        and settings.get("power_accounting") == "estimated"
    )
    learning = coordinator.power_learning
    if group and registry:
        context = learning_context(
            coordinator,
            group,
            tuple(m for m in registry.memberships if m.group_id == group.group_id),
        )
        if learning.context != context:
            learning = PowerLearning()
    learned = learning.learned(now) if enabled and supported else None
    return {
        "enabled": enabled,
        "supported": supported,
        "status": "disabled"
        if not enabled
        else "unsupported"
        if not supported
        else learning.status,
        "source": "learned"
        if learned is not None and learned > settings["estimated_ac_power"]
        else "configured",
        "confidence": "consistent" if learned is not None else "insufficient",
        "samples": len(learning.samples) if supported else 0,
        "learned_watts": learned,
        "configured_watts": settings["estimated_ac_power"],
        "effective_watts": max(settings["estimated_ac_power"], learned or 0),
        "updated_at": learning.updated_at if supported else None,
    }
