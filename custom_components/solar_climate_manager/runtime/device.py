"""State and synchronous policy evaluation for one climate device."""

from dataclasses import replace
from datetime import date, datetime
from typing import Any

from ..adapters.storage import demand_signature, restore_runtime, stored_state
from ..domain.sources import SourceSnapshot
from ..domain.types import (
    ControlIntent,
    DeviceConfig,
    EnergyPolicyConfig,
    ObservedDeviceState,
    PolicyState,
    StrategyDecision,
)
from ..manual import pause_active
from ..model import Decision, evaluate
from ..settings import OPERATION_MODES
from ..strategy import decide


class DeviceRuntime:
    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        self.demand = False
        self.signature = demand_signature(self.settings)
        self.observed = ObservedDeviceState()
        self.policy = PolicyState()
        self.intent = ControlIntent()
        self.device = DeviceConfig.from_settings(self.settings)
        self.manual_date: str | None = None
        self.previous_mode: str | None = None
        self.policy_signature = dict(self.settings)

    def restore(self, saved: Any, options: Any, now: float) -> None:
        self.signature = demand_signature(self.settings)
        restored = restore_runtime(
            saved, settings=self.settings,
            options=options, now=now,
        )
        self.demand = restored.demand
        self.manual_date = restored.manual_date
        self.previous_mode = restored.previous_mode
        self.observed = restored.observed
        self.policy = restored.policy

    def stored_state(self) -> dict[str, Any]:
        return stored_state(
            demand=self.demand, signature=self.signature, manual_date=self.manual_date,
            observed=self.observed, policy=self.policy, policy_signature=self.policy_signature,
        )

    def set_mode(
        self, mode: str, options: dict[str, Any], today: date
    ) -> dict[str, Any]:
        """Persist the visible mode and its midnight return state together."""
        if mode not in OPERATION_MODES:
            raise ValueError(mode)
        options = dict(options)
        if mode == "temporary_block":
            if self.settings["operation_mode"] != "temporary_block":
                self.previous_mode = self.settings["operation_mode"]
            self.manual_date = today.isoformat()
            options["temporary_previous_mode"] = self.previous_mode or "observation"
            options["temporary_block_date"] = self.manual_date
        else:
            self.manual_date = None
            self.previous_mode = None
            options.pop("temporary_previous_mode", None)
            options.pop("temporary_block_date", None)
        self.settings["operation_mode"] = mode
        self.device = replace(self.device, operation_mode=mode)
        self.policy.window.clear()
        self.signature = demand_signature(self.settings)
        self.policy_signature = dict(self.settings)
        options["operation_mode"] = mode
        options.pop("enabled", None)
        return options

    def mode_for_date(self, today: date) -> str | None:
        manual = pause_active(self.manual_date, today)
        if self.settings["operation_mode"] == "temporary_block" and not manual:
            return self.previous_mode or "observation"
        if manual and self.settings["operation_mode"] != "temporary_block":
            return "temporary_block"
        if self.manual_date and not manual:
            self.manual_date = None
        return None

    def evaluate(
        self, sources: SourceSnapshot, now: datetime, today: date
    ) -> tuple[Decision, StrategyDecision, bool]:
        manual = pause_active(self.manual_date, today)
        decision = evaluate(
            sources.temperature,
            target=self.device.target_temperature,
            hysteresis=self.device.hysteresis,
            mode=self.device.hvac_mode,
            previous_demand=self.demand,
            enabled=self.settings["operation_mode"] != "disabled",
            climate_valid=sources.climate_valid and sources.ac_target_temperature is not None,
        )
        self.demand = decision.demand
        if sources.running is not None:
            self.observed = self.observed.observe(sources.running, now.timestamp())
        evaluation = decide(
            sources.energy, self.observed, self.policy, EnergyPolicyConfig.from_settings(self.settings),
            now=now.timestamp(), demand=decision.demand,
            enabled=self.settings["operation_mode"] != "disabled", manual=manual,
        )
        self.policy = evaluation.policy
        strategy = evaluation.decision
        self.intent = strategy.intent
        return decision, strategy, manual
