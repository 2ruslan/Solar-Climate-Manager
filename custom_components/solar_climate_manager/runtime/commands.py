"""One command worker per device; service completion is not physical confirmation."""

import asyncio
import logging

from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from ..adapters.sources import climate_temperature
from ..climate_control import (
    ACKNOWLEDGEMENT_SECONDS,
    COMMAND_TIMEOUT_SECONDS,
    TARGET_UPDATE_SECONDS,
    acknowledgement_changes,
    compensated_target,
    compensation_needed,
    desired_fan_mode,
    matches_acknowledgement,
    normalized_target,
    temperature_matches,
)
from ..domain.types import CommandAttempt, CommandState, ControlIntent, ExpectedUpdate
from ..manual import pause_active

LOGGER = logging.getLogger(__name__)


class CommandExecutor:
    def __init__(self, hass, entry, runtime, get_data, evaluate, publish_error):
        self.hass = hass
        self.entry = entry
        self.runtime = runtime
        self.get_data = get_data
        self.evaluate = evaluate
        self.publish_error = publish_error
        self.state = CommandState()
        self.task = None
        self.closed = False
        self.authority = None
        self.device_id = None
        self.maintenance_target_active = False

    def schedule(self):
        if not self.closed and self.task is None and self.get_data()["control_allowed"]:
            self.task = self.entry.async_create_task(
                self.hass, self._async_control(), "climate control", eager_start=False
            )

    async def cancel(self):
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def shutdown(self):
        self.closed = True
        await self.cancel()

    def observe(self, climate):
        """Confirm only a new device report, including all commanded fields."""
        for attempt in (self.state.attempt, self.state.fan_attempt):
            self._observe_attempt(attempt, climate)

    def _observe_attempt(self, attempt, climate):
        if attempt is None or attempt.confirmed_at is not None or climate is None:
            return
        reported = getattr(climate, "last_reported", None)
        if reported is None or reported.timestamp() < attempt.sent_at:
            return
        for name, value in attempt.payload.items():
            if name == "hvac_mode":
                if climate.state != value:
                    return
            elif name == "temperature":
                if not temperature_matches(climate.attributes.get(name), value):
                    return
            elif climate.attributes.get(name) != value:
                return
        attempt.confirmed_at = reported.timestamp()

    def is_own_update(self, old, new):
        self._prune_acknowledgements()
        context = getattr(new, "context", None)
        if context is not None and not getattr(context, "user_id", None) and (
            context.id in self.state.contexts or context.parent_id in self.state.contexts
        ):
            return True
        return self._matches_expected_update(old, new, context)

    def _prune_acknowledgements(self):
        now = dt_util.utcnow().timestamp()
        self.state.contexts = {
            key: expires for key, expires in self.state.contexts.items() if expires >= now
        }
        self.state.expected_updates = [
            item for item in self.state.expected_updates if item.expires >= now and item.remaining
        ]

    def _matches_expected_update(self, old, new, context):
        # Explicit user commands and unrelated automation contexts remain manual.
        if context and (getattr(context, "user_id", None) or getattr(context, "parent_id", None)):
            return False
        changes = acknowledgement_changes(old, new)
        for item in self.state.expected_updates:
            if matches_acknowledgement(changes, item.remaining):
                for key in changes:
                    item.remaining.pop(key)
                return True
        return False

    def _set_command_error(self, error):
        self.state.error = error
        self.publish_error(error)

    def _control_command(self, climate, data=None):
        data = self.get_data() if data is None else data
        if self.runtime.intent.running:
            # Set fan speed only on a confirmed running device; never start an
            # off unit through a vendor-specific fan service before authorization.
            fan_mode = desired_fan_mode(
                self.runtime.device.target_temperature, data["temperature"], climate.attributes,
            )
            features = climate.attributes.get("supported_features")
            if (climate.state == self.runtime.device.hvac_mode and fan_mode is not None
                    and (features is None or features & 8)  # FAN_MODE
                    and climate.attributes.get("fan_mode") != fan_mode):
                return "set_fan_mode", {"fan_mode": fan_mode}
            try:
                normalized_target(
                    self.runtime.device.target_temperature,
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                )
                target = normalized_target(
                    self.runtime.device.target_temperature if not self.runtime.demand else compensated_target(
                        self.runtime.device.target_temperature,
                        data["temperature"],
                        data["ac_temperature"],
                    ),
                    climate.attributes,
                    self.hass.config.units.temperature_unit,
                    clamp=True,
                    bounds_c=(
                        self.runtime.device.ac_min_temperature, self.runtime.device.ac_max_temperature,
                    ),
                )
            except ValueError as error:
                self._set_command_error(str(error))
                return None
            mode = self.runtime.device.hvac_mode
            current_target = climate_temperature(
                climate, "temperature", self.hass.config.units.temperature_unit
            )
            current_valid = False
            if current_target is not None:
                try:
                    bounded_current = normalized_target(
                        current_target, climate.attributes,
                        self.hass.config.units.temperature_unit, clamp=True,
                        bounds_c=(
                            self.runtime.device.ac_min_temperature,
                            self.runtime.device.ac_max_temperature,
                        ),
                    )
                    current_valid = temperature_matches(
                        climate.attributes.get("temperature"), bounded_current
                    )
                except ValueError:
                    pass
            if climate.state == mode and (
                temperature_matches(climate.attributes.get("temperature"), target)
                or self.runtime.demand and not self.maintenance_target_active
                and current_valid and self.state.error == "none" and not compensation_needed(
                    current_target, data["ac_temperature"], mode
                )
            ):
                self.state.last_command = None
                self.state.unconfirmed_start = False
                self._set_command_error("none")
                self.maintenance_target_active = not self.runtime.demand
                return None
            return "set_temperature", {"hvac_mode": mode, "temperature": target}
        if climate.state == "off" and not self.state.unconfirmed_start:
            self.state.last_command = None
            self._set_command_error("none")
            return None
        return "set_hvac_mode", {"hvac_mode": "off"}

    async def _async_control(self):
        try:
            while (
                not self.closed
                and self.runtime.settings["operation_mode"] == "control"
                and self.get_data()["control_allowed"]
            ):
                climate = self.hass.states.get(self.runtime.settings["climate_entity"])
                if climate is None or climate.state in ("unknown", "unavailable"):
                    return
                if pause_active(self.runtime.manual_date, dt_util.now().date()):
                    return
                grouped = self.authority is not None and self.authority.controls(self.device_id)
                if grouped:
                    desired = self.authority.desired(self.device_id)
                    if desired is None:
                        return
                    self.runtime.intent = ControlIntent(desired)
                    if not desired and self.authority.has_pending(self.device_id):
                        self.state.unconfirmed_start = True
                command = self._control_command(climate)
                if command is None:
                    return
                service, payload = command
                key = (service, tuple(payload.items()))
                now = dt_util.utcnow().timestamp()
                if (
                    self.state.last_command
                    and self.state.last_command[0] == key
                    and now - self.state.last_command[1] < 30
                ):
                    return
                if (
                    service == "set_temperature"
                    and self.state.error == "none"
                    and self.state.last_target_update is not None
                    and now - self.state.last_target_update < TARGET_UPDATE_SECONDS
                ):
                    return
                ticket = None
                if grouped:
                    try:
                        ticket = await self.authority.async_authorize(self.device_id, service, payload, climate)
                    except (HomeAssistantError, OSError, ValueError):
                        self._set_command_error("service_error")
                        LOGGER.exception("Group command authorization failed")
                        return
                    if ticket is None:
                        return
                now = dt_util.utcnow().timestamp()
                self._prune_acknowledgements()
                context = Context()
                expires = now + ACKNOWLEDGEMENT_SECONDS
                self.state.contexts[context.id] = expires
                remaining = {
                    name: value
                    for name, value in payload.items()
                    if (climate.state if name == "hvac_mode" else climate.attributes.get(name))
                    != value
                }
                self.state.expected_updates.append(ExpectedUpdate(expires, remaining))
                attempt = CommandAttempt(service, dict(payload), now)
                if service == "set_fan_mode":
                    # Fan acknowledgement must not replace a pending start/stop
                    # acknowledgement used by group accounting and learning.
                    self.state.fan_attempt = attempt
                else:
                    self.state.attempt = attempt
                self.state.last_command = (key, now)
                if service == "set_temperature":
                    self.state.last_target_update = now
                    self.state.unconfirmed_start = True
                    self.maintenance_target_active = not self.runtime.demand
                try:
                    async with asyncio.timeout(COMMAND_TIMEOUT_SECONDS):
                        await self.hass.services.async_call(
                            "climate",
                            service,
                            {"entity_id": self.runtime.settings["climate_entity"], **payload},
                            blocking=True,
                            context=context,
                        )
                except asyncio.CancelledError:
                    attempt.service_status = "cancelled"
                    if ticket is not None:
                        await self.authority.async_finished(ticket, failed=True)
                    raise
                except (HomeAssistantError, TimeoutError):
                    attempt.service_status = "failed"
                    self._set_command_error("service_error")
                    LOGGER.exception("Climate command failed for entry %s", self.entry.entry_id)
                else:
                    attempt.service_status = "completed"
                    self._set_command_error("none")
                    if service == "set_hvac_mode":
                        self.state.unconfirmed_start = False
                if ticket is not None:
                    await self.authority.async_finished(ticket, failed=attempt.service_status != "completed")
                # Recompute after every service call: both state and timer deadlines
                # may have changed. A stop overrides an unconfirmed physical start.
                self.evaluate()
        finally:
            self.task = None
