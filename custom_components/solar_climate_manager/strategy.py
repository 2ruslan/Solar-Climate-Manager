"""Deterministic energy and comfort policy; device I/O belongs to the coordinator."""

from dataclasses import dataclass, field, fields
from math import isfinite

from .window import BudgetWindow

STRATEGY_DEFAULTS = {
    "estimated_ac_power": 900,
    "minimum_soc": 85,
    "restart_soc": 90,
    "max_battery_discharge": 100,
    "start_delay": 600,
    "shortage_delay": 600,
    "grid_absence_delay": 600,
    "minimum_run_time": 600,
    "minimum_off_time": 600,
    "grid_max_data_age": 86400,
    "load_includes_ac": True,
    "load_includes_battery_charging": False,
    "grid_on_means_available": True,
    "battery_positive": "discharge",
    "grid_positive": "import",
}

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
    forecasts: tuple = (None, None, None)
    actual_ac_power: float = 0  # actual measured or estimated draw
    ac_power_valid: bool = True
    temperature_valid: bool = True
    schedule_allowed: bool = True


@dataclass
class ControlState:
    running: bool = False
    last_start: float | None = None
    last_stop: float | None = None
    surplus_since: float | None = None
    deficit_since: float | None = None
    grid_absent_since: float | None = None
    soc_blocked: bool = False
    window: BudgetWindow = field(default_factory=BudgetWindow, repr=False)

    def restore(self, data, now):
        """Retain minimum-cycle deadlines; requalify continuity after downtime."""
        if not isinstance(data, dict):
            return
        self.last_start = valid_timestamp(data.get("last_start"), now)
        self.last_stop = valid_timestamp(data.get("last_stop"), now)
        self.running = data.get("running") is True and self.last_start is not None
        self.soc_blocked = data.get("soc_blocked") is True


def valid_timestamp(value, now):
    return (
        value
        if isinstance(value, (float, int))
        and not isinstance(value, bool)
        and isfinite(value)
        and 0 <= value <= now
        else None
    )


def remaining(now, since, duration):
    return max(0, duration - (now - since)) if since is not None else duration


def house_load_power(total, charge, includes_charging):
    """Remove measured charging exactly once, never battery discharge."""
    if total is None or not isfinite(total) or total < 0:
        return None
    if not includes_charging:
        return total
    if charge is None or not isfinite(charge) or charge < 0 or charge > total:
        return None
    return round(total - charge, 1)


@dataclass(frozen=True)
class StrategyDecision:
    action: str
    reason: str
    energy_allowed: bool
    running: bool
    solar_margin: float | None
    forecast_margin: float | None
    seconds_to_start: float | None = None
    seconds_to_stop: float | None = None
    average_solar_margin: float | None = None
    energy_reason: str = "invalid_energy_data"
    grid_import_margin: float | None = None


def decide(snapshot, state, settings, *, now, demand, enabled=True, manual=False):
    """Comfort from grid; protect low battery reserve and outage energy balance."""
    cfg = {**STRATEGY_DEFAULTS, **settings}
    solar_margin = forecast_margin = average_margin = None
    grid_import_margin = None
    observed = 0
    energy_allowed = False
    energy_reason = "invalid_energy_data"

    def result(action, reason, allowed=None, start=None, stop=None):
        return StrategyDecision(
            action,
            reason,
            energy_allowed if allowed is None else allowed,
            state.running,
            solar_margin,
            forecast_margin,
            start,
            stop,
            average_margin,
            energy_reason,
            grid_import_margin,
        )

    def halt(reason, *, reset_energy=True):
        was_running = state.running
        state.running = False
        if was_running:
            state.last_stop = now
        if reset_energy:
            state.surplus_since = state.deficit_since = None
        if reset_energy:
            state.window.clear()
        return result("stop" if was_running else "wait", reason)

    soc_valid = (
        snapshot.soc is not None
        and isfinite(snapshot.soc)
        and 0 <= snapshot.soc <= 100
    )
    if soc_valid:
        if snapshot.soc < cfg["minimum_soc"]:
            state.soc_blocked = True
        elif snapshot.soc >= cfg["restart_soc"]:
            state.soc_blocked = False
        if snapshot.grid is not True and (
            state.soc_blocked or not state.running and snapshot.soc < cfg["restart_soc"]
        ):
            state.soc_blocked = True
            energy_reason = "low_soc" if snapshot.soc < cfg["minimum_soc"] else "soc_recovery"
            return halt(energy_reason)
    if (
        snapshot.grid is None
        or any(value is None or not isfinite(value) for value in (snapshot.soc, snapshot.battery))
        or not 0 <= snapshot.soc <= 100
    ):
        state.grid_absent_since = None
        return halt("invalid_energy_data")

    if (
        snapshot.grid
        and state.soc_blocked
        and snapshot.battery > cfg["max_battery_discharge"]
    ):
        energy_reason = "battery_discharge"
        return halt(energy_reason)

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
        projected = snapshot.grid_power + (0 if state.running else cfg["estimated_ac_power"])
        grid_import_margin = round(limit - projected, 1)
        if grid_import_margin < 0:
            energy_reason = "grid_import_limit"
            return halt(energy_reason)

    if snapshot.grid:
        state.grid_absent_since = None
    elif state.grid_absent_since is None:
        state.grid_absent_since = now

    # Optional on-grid observations remain useful diagnostics, but cannot gate heating.
    house_load = house_load_power(
        snapshot.load, max(0, -snapshot.battery), cfg["load_includes_battery_charging"]
    )
    solar_valid = (
        snapshot.pv is not None
        and isfinite(snapshot.pv)
        and snapshot.pv >= 0
        and house_load is not None
        and snapshot.ac_power_valid
    )
    if solar_valid:
        base = (
            max(0, house_load - snapshot.actual_ac_power) if cfg["load_includes_ac"] else house_load
        )
        required = base + cfg["estimated_ac_power"]
        solar_margin = round(snapshot.pv - required, 1)
        state.window.observe(
            now,
            solar_margin,
            required,
            cfg["start_delay"],
        )
        average_margin, average_required, observed = state.window.average(now, cfg["start_delay"])
        average_margin = round(average_margin, 1)
        if snapshot.forecasts and all(
            value is not None and isfinite(value) and value >= 0 for value in snapshot.forecasts
        ):
            forecast_margin = round(min(snapshot.forecasts) - average_required, 1)
    else:
        state.window.clear()
        if not snapshot.grid:
            return halt("invalid_energy_data")

    if snapshot.grid:
        state.deficit_since = None
    elif solar_margin < 0:
        if state.deficit_since is None:
            state.deficit_since = now
    else:
        state.deficit_since = None
    shortage_left = (
        remaining(now, state.deficit_since, cfg["shortage_delay"])
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
    if state.running and not snapshot.grid and shortage_left is not None:
        outage_left = remaining(now, state.grid_absent_since, cfg["grid_absence_delay"])
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

    if state.running:
        run_left = remaining(now, state.last_start, cfg["minimum_run_time"])
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
    confirmation_left = 0 if snapshot.grid else max(0, cfg["start_delay"] - observed)
    off_left = (
        remaining(now, state.last_stop, cfg["minimum_off_time"])
        if state.last_stop is not None
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
    state.running = True
    state.last_start = now
    return result("start", "grid_ready" if snapshot.grid else "solar_ready", True)


def serialize(state):
    return {item.name: getattr(state, item.name) for item in fields(state) if item.name != "window"}
