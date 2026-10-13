"""Deterministic demo policy. Virtual transitions only; no device API imports."""

from dataclasses import dataclass, field, fields
from math import isfinite

from .window import BudgetWindow

STRATEGY_DEFAULTS = {
    "estimated_ac_power": 900,
    "minimum_soc": 85,
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

ACTIONS = ["would_start", "would_continue", "would_stop", "wait"]
REASONS = [
    "disabled",
    "manual_pause",
    "outside_schedule",
    "invalid_energy_data",
    "low_soc",
    "battery_discharge",
    "outage_deficit",
    "no_temperature_demand",
    "minimum_run",
    "insufficient_surplus",
    "start_confirmation",
    "minimum_off",
    "solar_ready",
    "grid_ready",
    "running",
]


@dataclass(frozen=True)
class EnergySnapshot:
    pv: float | None = None
    load: float | None = None
    soc: float | None = None
    battery: float | None = None  # positive = discharge
    grid_power: float | None = None  # positive = import
    grid: bool | None = None
    forecasts: tuple = (None, None, None)
    actual_ac_power: float = 0  # actual measured/verified draw, NEVER the virtual draw
    other_virtual_power: float = 0
    temperature_valid: bool = True
    schedule_allowed: bool = True


@dataclass
class DemoState:
    running: bool = False
    last_start: float | None = None
    last_stop: float | None = None
    surplus_since: float | None = None
    deficit_since: float | None = None
    grid_absent_since: float | None = None
    adverse_since: float | None = None
    discharge_blocked: bool = False
    window: BudgetWindow = field(default_factory=BudgetWindow, repr=False)

    def restore(self, data, now):
        """Retain minimum-cycle deadlines; requalify continuity after downtime."""
        if not isinstance(data, dict):
            return
        self.last_start = valid_timestamp(data.get("last_start"), now)
        self.last_stop = valid_timestamp(data.get("last_stop"), now)
        self.running = data.get("running") is True and self.last_start is not None
        self.discharge_blocked = data.get("discharge_blocked") is True


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
    virtual_running: bool
    solar_margin: float | None
    forecast_margin: float | None
    seconds_to_start: float | None = None
    seconds_to_stop: float | None = None
    average_solar_margin: float | None = None


def decide(snapshot, state, settings, *, now, demand, enabled=True, manual=False):
    """Comfort from grid; protect reserve during outages and sustained discharge."""
    cfg = {**STRATEGY_DEFAULTS, **settings}
    solar_margin = forecast_margin = average_margin = None
    observed = 0

    def result(action, reason, allowed=False, start=None, stop=None):
        return StrategyDecision(
            action,
            reason,
            allowed,
            state.running,
            solar_margin,
            forecast_margin,
            start,
            stop,
            average_margin,
        )

    def halt(reason):
        was_running = state.running
        state.running = False
        if was_running:
            state.last_stop = now
        state.surplus_since = state.deficit_since = state.adverse_since = None
        if reason == "battery_discharge":
            state.discharge_blocked = True
        state.window.clear()
        return result("would_stop" if was_running else "wait", reason)

    if not enabled:
        return halt("disabled")
    if manual:
        return halt("manual_pause")
    if not snapshot.schedule_allowed:
        return halt("outside_schedule")
    if (
        snapshot.soc is not None
        and isfinite(snapshot.soc)
        and 0 <= snapshot.soc <= 100
        and snapshot.soc < cfg["minimum_soc"]
    ):
        return halt("low_soc")
    if (
        not snapshot.temperature_valid
        or snapshot.grid is None
        or any(value is None or not isfinite(value) for value in (snapshot.soc, snapshot.battery))
        or not 0 <= snapshot.soc <= 100
    ):
        state.grid_absent_since = None
        return halt("invalid_energy_data")

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
    )
    if solar_valid:
        base = (
            max(0, house_load - snapshot.actual_ac_power) if cfg["load_includes_ac"] else house_load
        )
        required = base + cfg["estimated_ac_power"] + snapshot.other_virtual_power
        solar_margin = round(snapshot.pv - required, 1)
        state.window.observe(
            now,
            solar_margin + snapshot.other_virtual_power,
            required - snapshot.other_virtual_power,
            cfg["start_delay"],
        )
        average_margin, average_required, observed = state.window.average(now, cfg["start_delay"])
        average_margin = round(average_margin - snapshot.other_virtual_power, 1)
        if snapshot.forecasts and all(
            value is not None and isfinite(value) and value >= 0 for value in snapshot.forecasts
        ):
            forecast_margin = round(
                min(snapshot.forecasts) - average_required - snapshot.other_virtual_power, 1
            )
    else:
        state.window.clear()
        if not snapshot.grid:
            return halt("invalid_energy_data")

    # Short fridge/compressor spikes are tolerated; persistent actual discharge is not.
    if snapshot.battery > cfg["max_battery_discharge"]:
        if state.discharge_blocked:
            return halt("battery_discharge")
        if state.adverse_since is None:
            state.adverse_since = now
        discharge_left = remaining(now, state.adverse_since, cfg["shortage_delay"])
        if discharge_left == 0:
            return halt("battery_discharge")
    else:
        state.adverse_since = None
        state.discharge_blocked = False
        discharge_left = None

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

    if state.running:
        if not snapshot.grid and shortage_left is not None:
            outage_left = remaining(now, state.grid_absent_since, cfg["grid_absence_delay"])
            if shortage_left == 0 and outage_left == 0:
                return halt("outage_deficit")
            outage_deadline = max(shortage_left, outage_left)
        else:
            outage_deadline = None
        run_left = remaining(now, state.last_start, cfg["minimum_run_time"])
        if not demand and run_left == 0:
            return halt("no_temperature_demand")
        deadlines = [
            value
            for value in (discharge_left, outage_deadline, run_left if not demand else None)
            if value is not None
        ]
        reason = (
            "battery_discharge"
            if discharge_left is not None
            else "outage_deficit"
            if outage_deadline is not None
            else "minimum_run"
            if not demand
            else "grid_ready"
            if snapshot.grid
            else "running"
        )
        return result(
            "would_continue", reason, candidate, stop=min(deadlines) if deadlines else None
        )

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
    return result("would_start", "grid_ready" if snapshot.grid else "solar_ready", True)


def serialize(state):
    return {item.name: getattr(state, item.name) for item in fields(state) if item.name != "window"}
