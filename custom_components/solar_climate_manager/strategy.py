"""Deterministic energy and comfort policy; device I/O belongs to the command executor."""

from copy import deepcopy
from math import isfinite

from .domain.types import (
    Action,
    ControlIntent,
    EnergyPolicyConfig,
    EnergySnapshot,
    ObservedDeviceState,
    PolicyEvaluation,
    PolicyState,
    StrategyDecision,
)

STRATEGY_DEFAULTS = EnergyPolicyConfig().as_settings()

ACTIONS = ["start", "continue", "stop", "wait"]
REASONS = [
    "disabled",
    "manual_pause",
    "outside_schedule",
    "invalid_energy_data",
    "low_soc",
    "soc_recovery",
    "battery_discharge",
    "outage_deficit",
    "no_temperature_demand",
    "minimum_run",
    "insufficient_surplus",
    "start_confirmation",
    "minimum_off",
    "solar_ready",
    "grid_ready",
    "grid_import_limit",
    "grid_limit_unavailable",
    "grid_power_unavailable",
    "running",
]


def remaining(now: float, since: float | None, duration: float) -> float:
    return max(0, duration - (now - since)) if since is not None else duration


def house_load_power(
    total: float | None,
    charge: float | None,
    includes_charging: bool,
) -> float | None:
    """Remove measured charging exactly once, never battery discharge."""
    if total is None or not isfinite(total) or total < 0:
        return None
    if not includes_charging:
        return total
    if charge is None or not isfinite(charge) or charge < 0 or charge > total:
        return None
    return round(total - charge, 1)


def decide(
    snapshot: EnergySnapshot,
    observed_state: ObservedDeviceState,
    policy: PolicyState,
    cfg: EnergyPolicyConfig,
    *,
    now: float,
    demand: bool,
    enabled: bool = True,
    manual: bool = False,
) -> PolicyEvaluation:
    """Return an intent and next policy state without mutating any input."""
    state = deepcopy(policy)
    desired_running = observed_state.running
    solar_margin: float | None = None
    forecast_margin: float | None = None
    average_margin: float | None = None
    grid_import_margin: float | None = None
    observed = 0.0
    energy_allowed = False
    energy_reason = "invalid_energy_data"

    def result(
        action: Action,
        reason: str,
        allowed: bool | None = None,
        start: float | None = None,
        stop: float | None = None,
    ) -> PolicyEvaluation:
        return PolicyEvaluation(
            StrategyDecision(
                action,
                reason,
                energy_allowed if allowed is None else allowed,
                ControlIntent(desired_running),
                solar_margin,
                forecast_margin,
                start,
                stop,
                average_margin,
                energy_reason,
                grid_import_margin,
            ),
            state,
        )

    def halt(reason: str, *, reset_energy: bool = True) -> PolicyEvaluation:
        nonlocal desired_running
        was_running = observed_state.running
        desired_running = False
        if reset_energy:
            state.surplus_since = state.deficit_since = None
        if reset_energy:
            state.window.clear()
        return result("stop" if was_running else "wait", reason)

    soc_valid = snapshot.soc is not None and isfinite(snapshot.soc) and 0 <= snapshot.soc <= 100
    if soc_valid and snapshot.soc is not None:
        if snapshot.soc < cfg.minimum_soc:
            state.soc_blocked = True
        elif snapshot.soc >= cfg.restart_soc:
            state.soc_blocked = False
        if snapshot.grid is not True and (
            snapshot.soc < cfg.minimum_soc
            or not observed_state.running and snapshot.soc < cfg.restart_soc
        ):
            state.soc_blocked = True
            energy_reason = "low_soc" if snapshot.soc < cfg.minimum_soc else "soc_recovery"
            return halt(energy_reason)
    if (
        snapshot.grid is None
        or snapshot.soc is None
        or snapshot.battery is None
        or not isfinite(snapshot.soc)
        or not isfinite(snapshot.battery)
        or not 0 <= snapshot.soc <= 100
    ):
        state.grid_absent_since = None
        return halt("invalid_energy_data")

    if snapshot.grid and snapshot.grid_limit_configured and snapshot.grid_import_limit != 0:
        limit = snapshot.grid_import_limit
        if limit is None or not isfinite(limit) or limit < 0:
            energy_reason = "grid_limit_unavailable"
            return halt(energy_reason)
        if snapshot.grid_power is None or not isfinite(snapshot.grid_power):
            energy_reason = "grid_power_unavailable"
            return halt(energy_reason)
        # Grid metering already includes a running AC. Reserve its estimated
        # additional draw only before a start; signed export contributes headroom.
        projected = snapshot.grid_power + (0 if observed_state.running else cfg.estimated_ac_power)
        grid_import_margin = round(limit - projected, 1)
        if grid_import_margin < 0:
            energy_reason = "grid_import_limit"
            return halt(energy_reason)

    # A validated grid budget can supply the AC even while the inverter chooses
    # to discharge the battery for other loads. Keep the fallback protection
    # when no finite import budget is configured.
    if (
        snapshot.grid
        and grid_import_margin is None
        and state.soc_blocked
        and snapshot.battery > cfg.max_battery_discharge
    ):
        energy_reason = "battery_discharge"
        return halt(energy_reason)

    if snapshot.grid:
        state.grid_absent_since = None
    elif state.grid_absent_since is None:
        state.grid_absent_since = now

    # Optional on-grid observations remain useful diagnostics, but cannot gate heating.
    house_load = house_load_power(
        snapshot.load, max(0, -snapshot.battery), cfg.load_includes_battery_charging
    )
    solar_valid = (
        snapshot.pv is not None
        and isfinite(snapshot.pv)
        and snapshot.pv >= 0
        and house_load is not None
        and snapshot.ac_power_valid
    )
    if solar_valid and snapshot.pv is not None and house_load is not None:
        base = max(0, house_load - snapshot.actual_ac_power) if cfg.load_includes_ac else house_load
        required = base + cfg.estimated_ac_power
        solar_margin = round(snapshot.pv - required, 1)
        state.window.observe(
            now,
            solar_margin,
            required,
            cfg.start_delay,
        )
        average_margin, average_required, observed = state.window.average(now, cfg.start_delay)
        # observe() above guarantees at least one sample in the window.
        assert average_margin is not None and average_required is not None
        average_margin = round(average_margin, 1)
        if snapshot.forecasts and all(
            value is not None and isfinite(value) and value >= 0 for value in snapshot.forecasts
        ):
            forecasts = [value for value in snapshot.forecasts if value is not None]
            forecast_margin = round(min(forecasts) - average_required, 1)
    else:
        state.window.clear()
        if not snapshot.grid:
            return halt("invalid_energy_data")

    if snapshot.grid:
        state.deficit_since = None
    elif solar_margin is not None and solar_margin < 0:
        if state.deficit_since is None:
            state.deficit_since = now
    else:
        state.deficit_since = None
    shortage_left = (
        remaining(now, state.deficit_since, cfg.shortage_delay)
        if state.deficit_since is not None
        else None
    )
    candidate = snapshot.grid or (
        average_margin is not None
        and average_margin >= 0
        and (shortage_left is None or shortage_left > 0)
    )

    energy_allowed = bool(candidate)
    energy_reason = (
        "grid_ready" if snapshot.grid else "solar_ready" if candidate else "insufficient_surplus"
    )
    outage_deadline = None
    if observed_state.running and not snapshot.grid and shortage_left is not None:
        outage_left = remaining(now, state.grid_absent_since, cfg.grid_absence_delay)
        outage_deadline = max(shortage_left, outage_left)
        if outage_deadline == 0:
            energy_allowed = False
            energy_reason = "outage_deficit"
            return halt("outage_deficit")

    if not enabled:
        return halt("disabled", reset_energy=False)
    if manual:
        return halt("manual_pause", reset_energy=False)
    if not snapshot.schedule_allowed:
        return halt("outside_schedule", reset_energy=False)
    if not snapshot.temperature_valid:
        return halt("invalid_energy_data", reset_energy=False)

    if observed_state.running:
        run_left = remaining(now, observed_state.last_start, cfg.minimum_run_time)
        if not demand and run_left == 0:
            return halt("no_temperature_demand", reset_energy=False)
        deadlines = [
            value
            for value in (outage_deadline, run_left if not demand else None)
            if value is not None
        ]
        reason = (
            "outage_deficit"
            if outage_deadline is not None
            else "minimum_run"
            if not demand
            else "grid_ready"
            if snapshot.grid
            else "running"
        )
        return result("continue", reason, candidate, stop=min(deadlines) if deadlines else None)

    if not demand:
        return result("wait", "no_temperature_demand", candidate)
    if not candidate:
        return result("wait", "insufficient_surplus")
    confirmation_left = 0 if snapshot.grid else max(0, cfg.start_delay - observed)
    off_left = (
        remaining(now, observed_state.last_stop, cfg.minimum_off_time)
        if observed_state.last_stop is not None
        else 0
    )
    wait = max(confirmation_left, off_left)
    if wait:
        return result(
            "wait",
            "minimum_off" if off_left > confirmation_left else "start_confirmation",
            True,
            start=wait,
        )
    desired_running = True
    return result("start", "grid_ready" if snapshot.grid else "solar_ready", True)
