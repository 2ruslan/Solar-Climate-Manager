"""Deterministic demo policy. Virtual transitions only; no device API imports."""

from dataclasses import dataclass, field, fields
from math import isfinite

from .window import BudgetWindow

STRATEGY_DEFAULTS = {
    "estimated_ac_power": 900,
    "minimum_soc": 85,
    "prioritize_charging": True,
    "max_battery_discharge": 100,
    "allow_grid_import": False,
    "max_grid_import": 300,
    "start_delay": 600,
    "shortage_delay": 600,
    "grid_absence_delay": 600,
    "minimum_run_time": 600,
    "minimum_off_time": 600,
    "verification_delay": 180,
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
    "grid_import",
    "outage_deficit",
    "no_temperature_demand",
    "minimum_run",
    "insufficient_surplus",
    "forecast_insufficient",
    "start_confirmation",
    "minimum_off",
    "solar_ready",
    "grid_ready",
    "running",
    "energy_deficit",
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
    window: BudgetWindow = field(default_factory=BudgetWindow, repr=False)

    def restore(self, data, now):
        """Retain minimum-cycle deadlines; requalify continuity after downtime."""
        if not isinstance(data, dict):
            return
        self.last_start = valid_timestamp(data.get("last_start"), now)
        self.last_stop = valid_timestamp(data.get("last_stop"), now)
        self.running = data.get("running") is True and self.last_start is not None


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
    """Evaluate actual observations against a conservative incremental AC budget."""
    cfg = {**STRATEGY_DEFAULTS, **settings}
    solar_margin = forecast_margin = None
    average_margin = None

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
    values = (snapshot.pv, snapshot.load, snapshot.soc, snapshot.battery, snapshot.grid_power)
    if (
        not snapshot.temperature_valid
        or snapshot.grid is None
        or any(value is None or not isfinite(value) for value in values)
    ):
        state.grid_absent_since = None
        return halt("invalid_energy_data")
    if not 0 <= snapshot.soc <= 100 or snapshot.pv < 0 or snapshot.load < 0:
        return halt("invalid_energy_data")
    if snapshot.grid is False:
        if state.grid_absent_since is None:
            state.grid_absent_since = now
    else:
        state.grid_absent_since = None

    measured_charge = max(0, -snapshot.battery)
    house_load = house_load_power(
        snapshot.load, measured_charge, cfg["load_includes_battery_charging"]
    )
    if house_load is None:
        return halt("invalid_energy_data")
    charge_budget = 0
    if cfg["prioritize_charging"]:
        charge_budget = measured_charge
    base_load = (
        max(0, house_load - snapshot.actual_ac_power) if cfg["load_includes_ac"] else house_load
    )
    required = base_load + snapshot.other_virtual_power + cfg["estimated_ac_power"] + charge_budget
    solar_margin = round(snapshot.pv - required, 1)
    state.window.observe(
        now,
        solar_margin + snapshot.other_virtual_power,
        required - snapshot.other_virtual_power,
        cfg["start_delay"],
    )
    average_margin, average_required, observed = state.window.average(now, cfg["start_delay"])
    average_margin = round(average_margin - snapshot.other_virtual_power, 1)
    forecasts_valid = all(
        value is not None and isfinite(value) and value >= 0 for value in snapshot.forecasts
    )
    if forecasts_valid:
        forecast_margin = round(
            min(snapshot.forecasts) - average_required - snapshot.other_virtual_power, 1
        )
    forecast_start = forecasts_valid and forecast_margin >= 0
    forecast_hold = forecast_start
    if not forecasts_valid:
        return halt("invalid_energy_data")
    grid_limit = cfg["max_grid_import"] if cfg["allow_grid_import"] else 0
    actual_safe = (
        snapshot.battery <= cfg["max_battery_discharge"] and snapshot.grid_power <= grid_limit
    )
    additional_draw = (
        max(0, cfg["estimated_ac_power"] - snapshot.actual_ac_power) + snapshot.other_virtual_power
    )
    grid_ready = (
        cfg["allow_grid_import"]
        and snapshot.grid
        and max(0, snapshot.grid_power + additional_draw) <= cfg["max_grid_import"]
        and actual_safe
    )
    if not state.running:
        if not actual_safe and state.adverse_since is None:
            state.adverse_since = now
        if actual_safe:
            state.adverse_since = None
    limits_ok = (
        actual_safe
        or state.adverse_since is None
        or remaining(now, state.adverse_since, cfg["shortage_delay"]) > 0
    )
    solar_ready = average_margin >= 0 and forecast_start and limits_ok
    if not state.running:
        if solar_margin < 0 and not grid_ready:
            if state.deficit_since is None:
                state.deficit_since = now
        else:
            state.deficit_since = None
        if (
            state.deficit_since is not None
            and remaining(now, state.deficit_since, cfg["shortage_delay"]) == 0
        ):
            solar_ready = False
    candidate = solar_ready or grid_ready
    hold = solar_margin >= 0 and forecast_hold or grid_ready

    if state.running:
        run_left = remaining(now, state.last_start, cfg["minimum_run_time"])
        verification_left = remaining(now, state.last_start, cfg["verification_delay"])
        if not actual_safe:
            if state.adverse_since is None:
                state.adverse_since = now
            adverse_left = max(
                verification_left, remaining(now, state.adverse_since, cfg["shortage_delay"])
            )
            if adverse_left == 0:
                return halt(
                    "battery_discharge"
                    if snapshot.battery > cfg["max_battery_discharge"]
                    else "grid_import"
                )
        else:
            state.adverse_since = None
            adverse_left = None
        if not hold:
            if state.deficit_since is None:
                state.deficit_since = now
            shortage_left = remaining(now, state.deficit_since, cfg["shortage_delay"])
            outage_left = (
                remaining(now, state.grid_absent_since, cfg["grid_absence_delay"])
                if snapshot.grid is False
                else None
            )
            if outage_left is not None and outage_left == 0 and shortage_left == 0:
                return halt("outage_deficit")
            if shortage_left == 0 and run_left == 0 and snapshot.grid is True:
                return halt("energy_deficit")
        else:
            state.deficit_since = None
            shortage_left = outage_left = None
        if not demand and run_left == 0:
            return halt("no_temperature_demand")
        if not demand:
            return result("would_continue", "minimum_run", candidate, stop=run_left)
        deadlines = [
            value
            for value in (
                adverse_left,
                max(shortage_left, run_left)
                if shortage_left is not None and snapshot.grid is True
                else None,
                max(shortage_left, outage_left) if outage_left is not None else None,
            )
            if value is not None
        ]
        reason = "running"
        if shortage_left is not None:
            reason = "energy_deficit"
        if adverse_left is not None:
            reason = (
                "battery_discharge"
                if snapshot.battery > cfg["max_battery_discharge"]
                else "grid_import"
            )
        return result(
            "would_continue", reason, candidate, stop=min(deadlines) if deadlines else None
        )

    if not demand:
        state.surplus_since = None
        return result("wait", "no_temperature_demand", candidate)
    if not candidate:
        state.surplus_since = None
        reason = "insufficient_surplus" if average_margin < 0 else "forecast_insufficient"
        if not limits_ok and snapshot.battery > cfg["max_battery_discharge"]:
            reason = "battery_discharge"
        elif not limits_ok and snapshot.grid_power > grid_limit:
            reason = "grid_import"
        return result("wait", reason)
    state.surplus_since = None
    confirmation_left = max(0, cfg["start_delay"] - observed)
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
    state.adverse_since = None
    state.surplus_since = None
    return result(
        "would_start",
        "solar_ready" if solar_ready else "grid_ready",
        True,
    )


def serialize(state):
    return {item.name: getattr(state, item.name) for item in fields(state) if item.name != "window"}
