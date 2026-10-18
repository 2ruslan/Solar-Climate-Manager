"""Store v1 serialization and restoration; preserve existing keys and signatures."""

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from ..domain.types import ObservedDeviceState, PolicyState
from ..settings import BASE_MODES


def create_store(hass: Any, entry_id: str) -> Any:
    """Keep the storage API import out of pure serialization tests."""
    from homeassistant.helpers.storage import Store

    from ..const import DOMAIN

    return Store(hass, 1, f"{DOMAIN}.{entry_id}")


def valid_timestamp(value: object, now: float) -> float | None:
    return (
        value
        if isinstance(value, (float, int))
        and not isinstance(value, bool)
        and isfinite(value)
        and 0 <= value <= now
        else None
    )


def serialize(observed: ObservedDeviceState, policy: PolicyState) -> dict[str, Any]:
    """Keep the existing flat Store v1 shape while runtime states are separate."""
    return {
        **asdict(observed),
        "surplus_since": policy.surplus_since,
        "deficit_since": policy.deficit_since,
        "grid_absent_since": policy.grid_absent_since,
        "soc_blocked": policy.soc_blocked,
    }


def restore(data: Any, now: float) -> tuple[ObservedDeviceState, PolicyState]:
    """Retain physical cycle deadlines; requalify continuity after downtime."""
    if not isinstance(data, dict):
        return ObservedDeviceState(), PolicyState()
    last_start = valid_timestamp(data.get("last_start"), now)
    observed = ObservedDeviceState(
        running=data.get("running") is True and last_start is not None,
        last_start=last_start,
        last_stop=valid_timestamp(data.get("last_stop"), now),
    )
    return observed, PolicyState(soc_blocked=data.get("soc_blocked") is True)


def demand_signature(settings: dict[str, Any]) -> list[Any]:
    return [
        settings[key]
        for key in (
            "temperature_entity",
            "hvac_mode",
            "target_temperature",
            "hysteresis",
            "operation_mode",
        )
    ]


def stored_state(
    *,
    demand: bool,
    signature: list[Any],
    manual_date: str | None,
    observed: ObservedDeviceState,
    policy: PolicyState,
    policy_signature: dict[str, Any],
) -> dict[str, Any]:
    return {
        "demand": demand,
        "signature": list(signature),
        "manual_date": manual_date,
        "control": serialize(observed, policy),
        "policy_signature": dict(policy_signature),
    }


@dataclass(frozen=True)
class RestoredState:
    demand: bool
    observed: ObservedDeviceState
    policy: PolicyState
    manual_date: str | None
    previous_mode: str | None


def restore_runtime(
    saved: Any, *, settings: dict[str, Any], options: Any, now: float
) -> RestoredState:
    saved = saved if isinstance(saved, dict) else {}
    demand = saved.get("signature") == demand_signature(settings) and saved.get("demand") is True
    manual_date = saved.get("manual_date")
    previous_mode = None
    if settings["operation_mode"] == "temporary_block":
        manual_date = options.get("temporary_block_date", manual_date)
        previous = options.get("temporary_previous_mode")
        previous_mode = previous if previous in BASE_MODES else "observation"
    observed, policy = ObservedDeviceState(), PolicyState()
    signature = saved.get("policy_signature")
    if isinstance(signature, dict):
        signature = dict(signature)
        # Missing new parameters mean the unchanged pre-estimation behavior.
        for key, default in (("power_accounting", "legacy"), ("power_margin_percent", 20),
                             ("power_settle_seconds", 120), ("power_learning_enabled", False),
                             ("power_learning_generation", "")):
            if key in settings:
                signature.setdefault(key, default)
    if signature == settings:
        observed, policy = restore(saved.get("control"), now)
    elif isinstance(previous_control := saved.get("control"), dict):
        policy.soc_blocked = previous_control.get("soc_blocked") is True
        observed = ObservedDeviceState(
            last_stop=(
                now
                if previous_control.get("running") is True
                else valid_timestamp(previous_control.get("last_stop"), now)
            )
        )
    return RestoredState(demand, observed, policy, manual_date, previous_mode)
