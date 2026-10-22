"""Typed boundaries between observations, policy decisions and device commands."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any, Literal

from ..window import BudgetWindow

Action = Literal["start", "continue", "stop", "wait"]


@dataclass(frozen=True)
class DeviceConfig:
    climate_entity: str
    temperature_entity: str
    target_temperature: float = 23.0
    hysteresis: float = 1.0
    hvac_mode: str = "heat"
    ac_min_temperature: float = 15.0
    ac_max_temperature: float = 27.0
    operation_mode: str = "observation"
    schedule_entity: str | None = None

    @classmethod
    def from_settings(cls, values: Mapping[str, Any]) -> "DeviceConfig":
        """Consume already normalized HA data/options without changing their semantics."""
        return cls(**{item.name: values[item.name] for item in fields(cls) if item.name in values})


@dataclass(frozen=True)
class EnergyPolicyConfig:
    estimated_ac_power: float = 900
    minimum_soc: float = 85
    restart_soc: float = 90
    grid_absence_delay: float = 600
    minimum_run_time: float = 600
    minimum_off_time: float = 600
    load_includes_ac: bool = True
    load_includes_battery_charging: bool = False
    grid_on_means_available: bool = True
    battery_positive: str = "discharge"
    grid_positive: str = "import"

    @classmethod
    def from_settings(cls, values: Mapping[str, Any]) -> "EnergyPolicyConfig":
        return cls(**{item.name: values[item.name] for item in fields(cls) if item.name in values})

    def as_settings(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnergySnapshot:
    pv: float | None = None
    load: float | None = None
    soc: float | None = None
    battery: float | None = None  # positive = discharge
    grid_power: float | None = None  # positive = import
    grid_import_limit: float | None = None
    grid_limit_configured: bool = False
    grid: bool | None = None
    actual_ac_power: float = 0
    ac_power_valid: bool = True
    temperature_valid: bool = True
    schedule_allowed: bool = True


@dataclass(frozen=True)
class ObservedDeviceState:
    """Last known physical cycle, never a prediction of command success."""

    running: bool = False
    last_start: float | None = None
    last_stop: float | None = None

    def observe(self, running: bool, now: float) -> "ObservedDeviceState":
        if running == self.running:
            return self
        return replace(
            self,
            running=running,
            last_start=now if running else self.last_start,
            last_stop=self.last_stop if running else now,
        )


@dataclass
class PolicyState:
    surplus_since: float | None = None
    deficit_since: float | None = None
    grid_absent_since: float | None = None
    soc_blocked: bool = False
    window: BudgetWindow = field(default_factory=BudgetWindow, repr=False)


@dataclass(frozen=True)
class ControlIntent:
    running: bool = False


@dataclass(frozen=True)
class StrategyDecision:
    action: Action
    reason: str
    energy_allowed: bool
    intent: ControlIntent
    solar_margin: float | None
    seconds_to_start: float | None = None
    seconds_to_stop: float | None = None
    average_solar_margin: float | None = None
    energy_reason: str = "invalid_energy_data"
    grid_import_margin: float | None = None


@dataclass(frozen=True)
class PolicyEvaluation:
    decision: StrategyDecision
    policy: PolicyState


@dataclass
class ExpectedUpdate:
    expires: float
    remaining: dict[str, str | float]


@dataclass
class CommandAttempt:
    """Transport outcome and observed acknowledgement are independent facts."""

    service: str
    payload: dict[str, str | float]
    sent_at: float
    service_status: Literal["pending", "completed", "failed", "cancelled"] = "pending"
    confirmed_at: float | None = None


@dataclass
class CommandState:
    """In-flight command bookkeeping; it does not establish a physical cycle."""

    attempt: CommandAttempt | None = None
    contexts: dict[str, float] = field(default_factory=dict)
    expected_updates: list[ExpectedUpdate] = field(default_factory=list)
    unconfirmed_start: bool = False
    error: str = "none"
    last_command: tuple[tuple[str, tuple[tuple[str, str | float], ...]], float] | None = None
    last_target_update: float | None = None
