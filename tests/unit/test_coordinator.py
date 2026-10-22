"""Exercise the HA adapter locally with small in-memory event/storage boundaries."""

import asyncio
import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


def module(name, **attributes):
    item = types.ModuleType(name)
    item.__dict__.update(attributes)
    sys.modules[name] = item
    return item


class MemoryStore:
    saved = {}

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return self.saved.get(self.key)

    async def async_save(self, data):
        self.saved[self.key] = data

    def async_delay_save(self, callback, delay):
        self.saved[self.key] = callback()


class MemoryCoordinator:
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.data = None

    def async_set_updated_data(self, data):
        self.data = data


module("homeassistant")
module(
    "homeassistant.core",
    callback=lambda fn: fn,
    Context=lambda: SimpleNamespace(id="own-command", parent_id=None),
)
module("homeassistant.exceptions", HomeAssistantError=RuntimeError)
module(
    "homeassistant.const",
    Platform=SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor", SELECT="select"),
)
module("homeassistant.helpers")
module(
    "homeassistant.helpers.event",
    async_track_state_change_event=lambda *args: lambda: None,
    async_track_time_interval=lambda *args: lambda: None,
)
module("homeassistant.helpers.storage", Store=MemoryStore)
module("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=MemoryCoordinator)
clock = SimpleNamespace(current=datetime(2026, 10, 13, 12, tzinfo=timezone.utc))
dt = SimpleNamespace(
    utcnow=lambda: clock.current, now=lambda: clock.current.astimezone(timezone(timedelta(hours=3)))
)
module("homeassistant.util", dt=dt)
package = module("scm_adapter_test")
package.__path__ = [str(Path(__file__).parents[2] / "custom_components/solar_climate_manager")]
adapter = importlib.import_module("scm_adapter_test.coordinator")
constants = importlib.import_module("scm_adapter_test.const")


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        MemoryStore.saved.clear()
        clock.current = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        self.states = {}
        self.put("climate.ac", "off", hvac_modes=["heat", "cool", "off"], temperature=23)
        self.put("sensor.room", "20", unit_of_measurement="°C")
        for entity, value, unit in [
            ("sensor.pv", "2.8", "kW"),
            ("sensor.house", "600", "W"),
            ("sensor.soc", "95", "%"),
            ("sensor.battery", "0", "W"),
            ("sensor.grid", "0", "W"),
            ("sensor.forecast", "2800", "W"),
        ]:
            self.put(entity, value, unit_of_measurement=unit)
        self.put("binary_sensor.grid", "on")
        data = {
            **constants.DEFAULTS,
            "climate_entity": "climate.ac",
            "temperature_entity": "sensor.room",
            "pv_power_entity": "sensor.pv",
            "load_power_entity": "sensor.house",
            "soc_entity": "sensor.soc",
            "battery_power_entity": "sensor.battery",
            "grid_power_entity": "sensor.grid",
            "grid_available_entity": "binary_sensor.grid",
            "forecast_power_now_entity": "sensor.forecast",
            "forecast_power_30m_entity": "sensor.forecast",
            "forecast_power_60m_entity": "sensor.forecast",
            "start_delay": 60,
        }
        self.unload = []

        def entry_task(hass, coroutine, name=None, *, eager_start=True):
            self.assertFalse(eager_start)
            return asyncio.create_task(coroutine, name=name)

        self.entry = SimpleNamespace(
            data=data,
            options={},
            entry_id="test",
            async_on_unload=self.unload.append,
            async_create_task=entry_task,
        )
        self.hass = SimpleNamespace(
            async_create_task=asyncio.create_task,
            services=SimpleNamespace(async_call=AsyncMock()),
            config=SimpleNamespace(units=SimpleNamespace(temperature_unit="°C")),
            states=SimpleNamespace(get=self.states.get),
            config_entries=SimpleNamespace(
                async_entries=lambda domain: [self.entry],
                async_update_entry=lambda entry, **kw: setattr(entry, "options", kw["options"]),
            ),
        )
        self.coordinator = adapter.SolarClimateCoordinator(self.hass, self.entry)
        self.entry.runtime_data = self.coordinator
        await self.coordinator.async_initialize()

    def put(self, entity, state, **attributes):
        if entity.startswith("climate."):
            attributes.setdefault("current_temperature", 20)
        self.states[entity] = SimpleNamespace(
            state=state, attributes=attributes, last_reported=clock.current
        )

    async def test_observation_uses_physical_state_and_sends_no_commands(self):
        self.assertEqual(self.coordinator.data["strategy_action"], "start")
        clock.current += timedelta(seconds=600)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["strategy_action"], "start")
        self.assertFalse(self.coordinator.data["running"])
        self.assertFalse(self.coordinator.data["control_allowed"])
        self.assertEqual(self.states["climate.ac"].state, "off")

    async def test_manual_change_survives_reload_and_expires_locally(self):
        old = self.states["climate.ac"]
        self.put("climate.ac", "heat", hvac_modes=["heat", "cool", "off"], temperature=24)
        self.coordinator._state_changed(
            SimpleNamespace(
                data={
                    "entity_id": "climate.ac",
                    "old_state": old,
                    "new_state": self.states["climate.ac"],
                }
            )
        )
        self.assertTrue(self.coordinator.data["manual_pause"])
        self.assertEqual(self.coordinator.settings["operation_mode"], "temporary_block")
        self.assertEqual(self.entry.options["temporary_previous_mode"], "observation")
        await self.coordinator.async_shutdown()
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        self.entry.runtime_data = new
        await new.async_initialize()
        self.assertEqual(new.data["strategy_reason"], "manual_pause")
        clock.current += timedelta(days=1)
        for state in self.states.values():
            state.last_reported = clock.current
        new._evaluate()
        self.assertFalse(new.data["manual_pause"])
        self.assertEqual(new.data["automation_mode"], "observation")
        self.assertEqual(new.data["strategy_action"], "continue")

    async def test_temporary_block_returns_each_previous_mode_at_local_midnight(self):
        for mode in ("disabled", "observation", "control"):
            clock.current = datetime(2026, 10, 13, 20, 59, tzinfo=timezone.utc)
            await self.coordinator.async_set_mode(mode)
            await self.coordinator.async_set_mode("temporary_block")
            # Repeated blocking must retain the original return mode.
            await self.coordinator.async_set_mode("temporary_block")
            self.assertEqual(self.entry.options["temporary_previous_mode"], mode)
            self.assertFalse(self.coordinator.data["control_allowed"])
            await self.coordinator.async_shutdown()
            new = adapter.SolarClimateCoordinator(self.hass, self.entry)
            await new.async_initialize()
            self.assertEqual(new.data["automation_mode"], "temporary_block")
            clock.current += timedelta(minutes=1)
            new._tick(clock.current)
            self.assertEqual(new.data["automation_mode"], mode)
            self.assertFalse(new.data["manual_pause"])
            self.assertNotIn("temporary_previous_mode", self.entry.options)
            await new.async_shutdown()
            self.coordinator = adapter.SolarClimateCoordinator(self.hass, self.entry)
            await self.coordinator.async_initialize()
        await self.coordinator.async_shutdown()
        self.hass.services.async_call.assert_not_called()

    async def test_selecting_mode_clears_block_and_prevents_midnight_reversion(self):
        await self.coordinator.async_set_mode("control")
        await self.coordinator.async_set_mode("temporary_block")
        await self.coordinator.async_set_mode("disabled")
        self.assertIsNone(self.coordinator.runtime.manual_date)
        clock.current += timedelta(days=1)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["automation_mode"], "disabled")
        await self.coordinator.async_set_mode("temporary_block")
        await self.coordinator.async_set_mode("control")
        self.assertTrue(self.coordinator.data["control_allowed"])
        self.assertFalse(self.coordinator.data["manual_pause"])
        await self.coordinator.async_shutdown()

    async def test_legacy_manual_pause_migrates_to_visible_block(self):
        await self.coordinator.async_shutdown()
        saved = MemoryStore.saved[self.coordinator.store.key]
        saved["manual_date"] = dt.now().date().isoformat()
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertEqual(new.data["automation_mode"], "temporary_block")
        self.assertEqual(new.runtime.previous_mode, "observation")

    async def test_temporary_block_survives_restart_after_midnight(self):
        await self.coordinator.async_set_mode("disabled")
        await self.coordinator.async_set_mode("temporary_block")
        await self.coordinator.async_shutdown()
        clock.current += timedelta(days=1)
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertEqual(new.data["automation_mode"], "disabled")
        self.assertFalse(new.data["manual_pause"])

    async def test_external_changes_keep_control_return_mode_after_settings_edit(self):
        await self.coordinator.async_set_mode("control")
        for target in (24, 25):
            old = self.states["climate.ac"]
            self.put("climate.ac", "heat", hvac_modes=["heat", "off"], temperature=target)
            self.coordinator._state_changed(
                SimpleNamespace(data={
                    "entity_id": "climate.ac",
                    "old_state": old,
                    "new_state": self.states["climate.ac"],
                })
            )
            self.assertEqual(self.coordinator.data["automation_mode"], "temporary_block")
            self.assertEqual(self.coordinator.runtime.previous_mode, "control")
        await self.coordinator.async_shutdown()
        values = adapter.configuration_values(
            self.entry.data, self.entry.options, constants.DEFAULTS, constants.REMOVED_SETTINGS
        )
        self.entry.options = {**values, "target_temperature": 22}
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertEqual(new.data["automation_mode"], "temporary_block")
        self.assertEqual(new.runtime.previous_mode, "control")
        self.assertFalse(new.data["control_allowed"])
        self.hass.services.async_call.assert_not_called()

    async def test_signed_sources_and_old_soc_remain_valid(self):
        self.coordinator.settings["battery_positive"] = "charge"
        self.put("sensor.battery", "-500", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["battery_power"], 500)
        clock.current += timedelta(seconds=601)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["strategy_reason"], "grid_ready")
        self.states["sensor.soc"].last_reported = clock.current - timedelta(seconds=901)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["soc"], 95)
        self.assertFalse(self.coordinator.data["energy_data_invalid"])

    async def test_retired_forecast_is_ignored_and_old_measurements_remain_valid(self):
        self.states["sensor.forecast"].last_reported = clock.current - timedelta(days=2)
        self.coordinator._evaluate()
        self.assertNotIn("forecast_power_now", self.coordinator.data)
        self.assertTrue(self.coordinator.data["energy_allowed"])
        self.states["sensor.pv"].last_reported = clock.current - timedelta(seconds=901)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["pv_power"], 2800)
        self.assertEqual(self.coordinator.data["strategy_reason"], "grid_ready")

    async def test_removed_settings_ignored_on_existing_entry(self):
        self.entry.options = {
            "forecast_detail_entity": "sensor.missing_detail",
            "forecast_power_now_entity": "sensor.forecast",
            "forecast_power_30m_entity": "sensor.forecast",
            "forecast_power_60m_entity": "sensor.forecast",
            "forecast_updated_entity": "sensor.missing_timestamp",
            "forecast_max_data_age": 1,
            "forecast_horizon": 30,
        }
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        self.entry.runtime_data = new
        await new.async_initialize()
        for key in constants.REMOVED_FORECAST_SETTINGS:
            self.assertNotIn(key, new.settings)
        self.assertTrue(new.data["energy_allowed"])

    async def test_unavailable_forecast_is_not_a_cached_numeric_value(self):
        self.put("sensor.forecast", "unavailable", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertNotIn("forecast_power_now", self.coordinator.data)
        self.assertEqual(self.coordinator.data["strategy_reason"], "grid_ready")

    async def test_configured_ac_meter_missing_is_not_silently_estimated(self):
        self.coordinator.settings["ac_power_entity"] = "sensor.ac_missing"
        self.coordinator._evaluate()
        self.assertFalse(self.coordinator.data["energy_data_invalid"])
        self.assertEqual(self.coordinator.data["strategy_reason"], "grid_ready")

    async def test_inclusive_load_and_signed_charge_mapping(self):
        self.coordinator.settings["load_includes_battery_charging"] = True
        self.put("sensor.house", "1.6", unit_of_measurement="kW")
        self.put("sensor.battery", "-1000", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["load_power"], 1600)
        self.assertEqual(self.coordinator.data["house_load_power"], 600)
        self.assertEqual(self.coordinator.data["battery_charge_power"], 1000)
        self.assertEqual(self.coordinator.data["solar_margin"], 1300)
        self.put("sensor.battery", "unavailable")
        self.coordinator._evaluate()
        self.assertIsNone(self.coordinator.data["house_load_power"])
        self.assertTrue(self.coordinator.data["energy_data_invalid"])

    async def test_legacy_charge_source_ignored_after_update(self):
        self.entry.options = {"battery_charge_power_entity": "sensor.missing_charge"}
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        self.entry.runtime_data = new
        await new.async_initialize()
        self.assertNotIn("battery_charge_power_entity", new.settings)
        self.assertEqual(new.data["battery_charge_power"], 0)
        self.assertTrue(new.data["energy_allowed"])

    async def control_mode(self):
        await self.coordinator.async_set_mode("control")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task

    def own_update(self, mode="heat", temperature=23):
        old = self.states["climate.ac"]
        self.put("climate.ac", mode, hvac_modes=["heat", "cool", "off"], temperature=temperature)
        self.states["climate.ac"].context = SimpleNamespace(id="own-command", parent_id=None)
        self.coordinator._state_changed(
            SimpleNamespace(
                data={
                    "entity_id": "climate.ac",
                    "old_state": old,
                    "new_state": self.states["climate.ac"],
                }
            )
        )

    async def test_control_starts_actual_climate_and_own_update_does_not_pause(self):
        await self.control_mode()
        call = self.hass.services.async_call.call_args
        self.assertEqual(call.args[:2], ("climate", "set_temperature"))
        self.assertEqual(
            call.args[2], {"entity_id": "climate.ac", "hvac_mode": "heat", "temperature": 23}
        )
        self.own_update()
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.assertFalse(self.coordinator.data["manual_pause"])
        self.assertTrue(self.coordinator.data["running"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_outdoor_guard_sends_stop_in_control_mode(self):
        self.coordinator.settings["outdoor_temperature_entity"] = "sensor.outdoor"
        self.put("sensor.outdoor", "0", unit_of_measurement="°C")
        await self.control_mode()
        self.own_update()
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("sensor.outdoor", "-6", unit_of_measurement="°C")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.coordinator.data["strategy_reason"], "low_outdoor_temperature")
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "off")

    async def test_low_soc_stops_actual_climate(self):
        await self.control_mode()
        self.own_update()
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("binary_sensor.grid", "off")
        self.put("sensor.soc", "40", unit_of_measurement="%")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.call_args.args[1], "set_hvac_mode")
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "off")

    async def test_soc_block_survives_settings_reload(self):
        self.put("binary_sensor.grid", "off")
        self.put("sensor.soc", "84", unit_of_measurement="%")
        self.coordinator._evaluate()
        self.assertTrue(self.coordinator.runtime.policy.soc_blocked)
        await self.coordinator.async_shutdown()
        self.entry.options = {"target_temperature": 24}
        self.put("sensor.soc", "88", unit_of_measurement="%")
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertEqual(new.data["energy_reason"], "soc_recovery")
        self.assertTrue(new.data["soc_blocked"])
        self.put("sensor.soc", "90", unit_of_measurement="%")
        new._evaluate()
        self.assertFalse(new.data["soc_blocked"])

    async def test_disabled_and_observation_never_send_commands_and_persist(self):
        for mode in ("disabled", "observation"):
            self.put("climate.ac", "heat", hvac_modes=["heat", "cool", "off"], temperature=23)
            await self.coordinator.async_set_mode(mode)
            self.assertFalse(self.coordinator.data["control_allowed"])
            self.assertEqual(self.entry.options["operation_mode"], mode)
            new = adapter.SolarClimateCoordinator(self.hass, self.entry)
            await new.async_initialize()
            self.assertEqual(new.data["automation_mode"], mode)
        self.hass.services.async_call.assert_not_called()

    async def test_mode_change_cancels_queued_command(self):
        await self.coordinator.async_set_mode("control")
        await self.coordinator.async_set_mode("observation")
        await asyncio.sleep(0)
        self.hass.services.async_call.assert_not_called()

    async def test_control_temperature_in_fahrenheit(self):
        self.hass.config.units.temperature_unit = "°F"
        self.states["climate.ac"].attributes["current_temperature"] = 68
        await self.control_mode()
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 73.4)

    async def test_unavailable_and_manual_pause_do_not_send_commands(self):
        self.put("climate.ac", "unavailable", hvac_modes=["heat"])
        await self.control_mode()
        self.hass.services.async_call.assert_not_called()
        self.put("climate.ac", "heat", hvac_modes=["heat", "cool", "off"], temperature=24)
        self.coordinator.runtime.manual_date = dt.now().date().isoformat()
        self.coordinator._evaluate()
        self.hass.services.async_call.assert_not_called()

    async def test_command_failure_retries_without_simulating_success(self):
        self.hass.services.async_call.side_effect = RuntimeError("device unavailable")
        with self.assertLogs("scm_adapter_test.runtime.commands", level="ERROR"):
            await self.control_mode()
        self.assertFalse(self.coordinator.data["running"])
        clock.current += timedelta(seconds=30)
        self.coordinator._evaluate()
        with self.assertLogs("scm_adapter_test.runtime.commands", level="ERROR"):
            await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.await_count, 2)

    async def test_unchanged_temperature_keeps_graph_and_control_available(self):
        await self.control_mode()
        self.own_update()
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        # The source reports only when its reading changes, including across ticks.
        for age in (901, 7200, 172800):
            self.states["sensor.room"].last_reported = clock.current - timedelta(seconds=age)
            self.coordinator._evaluate()
            await self.coordinator.commands.task
            self.assertEqual(self.coordinator.data["temperature"], 20)
            self.assertFalse(self.coordinator.data["invalid_data"])
            self.assertTrue(self.coordinator.data["demand"])
            self.assertTrue(self.coordinator.data["running"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_unavailable_temperature_keeps_last_value_and_actual_climate_running(self):
        await self.control_mode()
        self.own_update()
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("sensor.room", "unavailable", unit_of_measurement="°C")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.coordinator.data["temperature"], 20)
        self.assertFalse(self.coordinator.data["invalid_data"])
        self.assertTrue(self.coordinator.data["running"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_last_temperature_survives_reload_while_sensor_unavailable(self):
        await self.coordinator.async_shutdown()
        self.put("sensor.room", "unavailable", unit_of_measurement="°C")
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertEqual(new.data["temperature"], 20)
        self.assertTrue(new.data["demand"])
        self.put("sensor.room", "25", unit_of_measurement="°C")
        new._evaluate()
        self.assertEqual(new.data["temperature"], 25)
        self.assertFalse(new.data["demand"])
        await new.async_shutdown()

    async def test_cached_temperature_does_not_transfer_to_another_sensor(self):
        await self.coordinator.async_shutdown()
        self.entry.options["temperature_entity"] = "sensor.other_room"
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertIsNone(new.data["temperature"])
        self.assertTrue(new.data["invalid_data"])
        await new.async_shutdown()

    async def test_old_temperature_survives_reload_and_updates_when_source_changes(self):
        self.entry.options["max_data_age"] = 1
        self.states["sensor.room"].last_reported = clock.current - timedelta(days=2)
        await self.coordinator.async_shutdown()
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        self.entry.runtime_data = new
        await new.async_initialize()
        self.assertNotIn("max_data_age", new.settings)
        self.assertEqual(new.data["temperature"], 20)
        self.assertTrue(new.data["demand"])
        self.put("sensor.room", "25", unit_of_measurement="°C")
        new._evaluate()
        self.assertEqual(new.data["temperature"], 25)
        self.assertFalse(new.data["demand"])
        for value in ("unknown", "unavailable", "nan", "bad"):
            self.put("sensor.room", value, unit_of_measurement="°C")
            new._evaluate()
            self.assertEqual(new.data["temperature"], 25)
            self.assertFalse(new.data["invalid_data"])
        del self.states["sensor.room"]
        new._evaluate()
        self.assertEqual(new.data["temperature"], 25)
        self.assertFalse(new.data["invalid_data"])

    async def test_cooling_command(self):
        self.coordinator.settings["hvac_mode"] = "cool"
        self.put("sensor.room", "28", unit_of_measurement="°C")
        await self.control_mode()
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "cool")

    async def test_temperature_satisfied_lowers_target_and_keeps_running(self):
        await self.control_mode()
        self.own_update()
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("sensor.room", "25", unit_of_measurement="°C")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.await_count, 1)
        clock.current += timedelta(seconds=600)
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        payload = self.hass.services.async_call.call_args.args[2]
        self.assertEqual(payload["hvac_mode"], "heat")
        self.assertEqual(payload["temperature"], self.coordinator.settings["target_temperature"])
        self.assertEqual(self.coordinator.data["strategy_reason"], "temperature_maintenance")
        maintenance_target = payload["temperature"]
        self.own_update(temperature=maintenance_target)
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        clock.current += timedelta(seconds=61)
        self.states["climate.ac"].attributes["current_temperature"] = 26
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.coordinator.data["ac_target_temperature"], maintenance_target)
        self.assertEqual(self.hass.services.async_call.await_count, 1)
        self.put("sensor.room", "20", unit_of_measurement="°C")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        payload = self.hass.services.async_call.call_args.args[2]
        self.assertEqual(payload["hvac_mode"], "heat")
        self.assertGreater(payload["temperature"], maintenance_target)
        self.assertTrue(self.coordinator.data["demand"])

    async def test_cooling_maintenance_raises_target_instead_of_switching_off(self):
        self.coordinator.settings["hvac_mode"] = "cool"
        self.put("sensor.room", "28", unit_of_measurement="°C")
        await self.control_mode()
        initial_target = self.hass.services.async_call.call_args.args[2]["temperature"]
        self.own_update(mode="cool", temperature=initial_target)
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        clock.current += timedelta(seconds=601)
        self.put("sensor.room", "20", unit_of_measurement="°C")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        payload = self.hass.services.async_call.call_args.args[2]
        self.assertEqual(payload["hvac_mode"], "cool")
        self.assertGreater(payload["temperature"], initial_target)
        self.assertEqual(payload["temperature"], self.coordinator.settings["target_temperature"])
        self.assertEqual(self.coordinator.data["strategy_reason"], "temperature_maintenance")

    async def test_shutdown_cancels_pending_command(self):
        await self.coordinator.async_set_mode("control")
        await self.coordinator.async_shutdown()
        await asyncio.sleep(0)
        self.hass.services.async_call.assert_not_called()

    def device_response(self, mode, **updates):
        old = self.states["climate.ac"]
        self.put("climate.ac", mode, **{**old.attributes, **updates})
        new = self.states["climate.ac"]
        new.context = SimpleNamespace(id="device-report", parent_id=None, user_id=None)
        self.coordinator._state_changed(
            SimpleNamespace(data={"entity_id": "climate.ac", "old_state": old, "new_state": new})
        )

    async def test_mode_change_cancels_active_service_without_confirming_it(self):
        async def hang(*args, **kwargs):
            await asyncio.Event().wait()

        self.hass.services.async_call.side_effect = hang
        await self.coordinator.async_set_mode("control")
        await asyncio.sleep(0)
        attempt = self.coordinator.commands.state.attempt
        await self.coordinator.async_set_mode("observation")
        self.assertEqual(attempt.service_status, "cancelled")
        self.assertIsNone(attempt.confirmed_at)
        self.assertIsNone(self.coordinator.commands.task)
        self.assertFalse(self.coordinator.runtime.observed.running)
        self.assertTrue(self.coordinator.commands.state.unconfirmed_start)
        await self.coordinator.async_shutdown()

    async def test_diagnostics_reads_manual_state_from_device_runtime(self):
        await self.coordinator.async_set_mode("temporary_block")
        diagnostics = importlib.import_module("scm_adapter_test.diagnostics")
        exported = await diagnostics.async_get_config_entry_diagnostics(self.hass, self.entry)
        self.assertEqual(exported["manual_until_date"], self.coordinator.runtime.manual_date)

    async def test_service_completion_requires_full_device_confirmation(self):
        self.coordinator.settings["target_temperature"] = 24
        await self.control_mode()
        attempt = self.coordinator.commands.state.attempt
        self.assertEqual(attempt.service_status, "completed")
        self.assertIsNone(attempt.confirmed_at)
        self.assertFalse(self.coordinator.runtime.observed.running)
        self.device_response("heat")
        self.assertIsNone(attempt.confirmed_at)
        self.assertTrue(self.coordinator.runtime.observed.running)
        clock.current += timedelta(seconds=1)
        self.device_response("heat", temperature=24)
        self.assertEqual(attempt.confirmed_at, clock.current.timestamp())
        await self.coordinator.async_shutdown()

    async def test_stop_timeout_keeps_physical_running_and_no_confirmation(self):
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("binary_sensor.grid", "off")
        self.put("sensor.soc", "40", unit_of_measurement="%")

        async def hang(*args, **kwargs):
            await asyncio.Event().wait()

        self.hass.services.async_call.side_effect = hang
        commands = importlib.import_module("scm_adapter_test.runtime.commands")
        with patch.object(commands, "COMMAND_TIMEOUT_SECONDS", 0.001):
            with self.assertLogs(commands.LOGGER, level="ERROR"):
                self.coordinator._evaluate()
                await self.coordinator.commands.task
        attempt = self.coordinator.commands.state.attempt
        self.assertEqual(attempt.service, "set_hvac_mode")
        self.assertEqual(attempt.service_status, "failed")
        self.assertIsNone(attempt.confirmed_at)
        self.assertTrue(self.coordinator.runtime.observed.running)
        self.assertIsNone(self.coordinator.runtime.observed.last_stop)
        self.device_response("off")
        self.assertIsNotNone(attempt.confirmed_at)
        self.assertFalse(self.coordinator.runtime.observed.running)
        await self.coordinator.async_shutdown()

    async def test_manual_change_during_service_prevents_followup_commands(self):
        release = asyncio.Event()

        async def slow(*args, **kwargs):
            await release.wait()

        self.hass.services.async_call.side_effect = slow
        await self.coordinator.async_set_mode("control")
        worker = self.coordinator.commands.task
        await asyncio.sleep(0)
        for _ in range(5):
            self.coordinator._evaluate()
            self.assertIs(self.coordinator.commands.task, worker)
        self.device_response("cool", temperature=19)
        self.assertEqual(self.coordinator.settings["operation_mode"], "temporary_block")
        release.set()
        await worker
        self.assertEqual(self.hass.services.async_call.await_count, 1)
        self.assertIsNone(self.coordinator.commands.task)
        self.assertIsNone(self.coordinator.commands.state.attempt.confirmed_at)
        await self.coordinator.async_shutdown()

    async def test_shutdown_cancels_service_and_ignores_late_events(self):
        async def hang(*args, **kwargs):
            await asyncio.Event().wait()

        self.hass.services.async_call.side_effect = hang
        await self.coordinator.async_set_mode("control")
        await asyncio.sleep(0)
        attempt = self.coordinator.commands.state.attempt
        await self.coordinator.async_shutdown()
        self.assertEqual(attempt.service_status, "cancelled")
        self.assertIsNone(attempt.confirmed_at)
        saved = self.coordinator._stored_state()
        self.device_response("heat")
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator._stored_state(), saved)
        self.assertIsNone(self.coordinator.commands.task)
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_contextless_response_does_not_pause(self):
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.assertFalse(self.coordinator.data["manual_pause"])
        self.assertTrue(self.coordinator.data["energy_allowed"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_split_contextless_response_does_not_pause(self):
        self.coordinator.settings["target_temperature"] = 24
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.device_response("heat", temperature=24)
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.assertFalse(self.coordinator.data["manual_pause"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_uncommanded_fan_change_is_manual_even_during_ack_window(self):
        await self.control_mode()
        self.device_response("heat", fan_mode="quiet")
        self.assertTrue(self.coordinator.data["manual_pause"])
        self.assertTrue(self.coordinator.data["energy_allowed"])

    async def test_expired_contextless_acknowledgement_is_manual(self):
        await self.control_mode()
        clock.current += timedelta(seconds=31)
        self.device_response("heat")
        self.assertTrue(self.coordinator.data["manual_pause"])

    async def test_explicit_user_command_is_manual_even_if_it_matches_expected(self):
        await self.control_mode()
        old = self.states["climate.ac"]
        self.put("climate.ac", "heat", **old.attributes)
        new = self.states["climate.ac"]
        new.context = SimpleNamespace(id="user-command", parent_id=None, user_id="user")
        self.coordinator._state_changed(
            SimpleNamespace(data={"entity_id": "climate.ac", "old_state": old, "new_state": new})
        )
        self.assertTrue(self.coordinator.data["manual_pause"])

    async def test_quantized_temperature_is_not_sent_repeatedly(self):
        self.coordinator.settings["target_temperature"] = 23.5
        self.states["climate.ac"].attributes.update(min_temp=16, max_temp=30, target_temp_step=1)
        await self.control_mode()
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 24)
        self.device_response("heat", temperature=24)
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        for _ in range(3):
            clock.current += timedelta(seconds=30)
            self.coordinator._evaluate()
            await self.coordinator.commands.task
        self.assertFalse(self.coordinator.data["manual_pause"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_out_of_range_runtime_target_is_visible_and_not_sent(self):
        self.coordinator.settings["target_temperature"] = 35
        self.states["climate.ac"].attributes.update(min_temp=16, max_temp=30)
        await self.control_mode()
        self.hass.services.async_call.assert_not_called()
        self.assertEqual(self.coordinator.data["command_error"], "invalid_target")
        self.assertTrue(self.coordinator.data["command_failed"])

    async def test_command_failure_visible_and_clears_after_success(self):
        self.hass.services.async_call.side_effect = RuntimeError("offline")
        with self.assertLogs("scm_adapter_test.runtime.commands", level="ERROR"):
            await self.control_mode()
        self.assertEqual(self.coordinator.data["command_error"], "service_error")
        self.assertTrue(self.coordinator.data["command_failed"])
        self.hass.services.async_call.side_effect = None
        clock.current += timedelta(seconds=30)
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.coordinator.data["command_error"], "none")
        self.assertFalse(self.coordinator.data["command_failed"])

    async def test_pending_start_is_followed_immediately_by_protective_stop(self):
        for report_start in (True, False):
            await self.asyncSetUp()
            release = asyncio.Event()

            async def slow_start(domain, service, data, **kwargs):
                if service == "set_temperature":
                    await release.wait()

            self.hass.services.async_call.side_effect = slow_start
            await self.coordinator.async_set_mode("control")
            worker = self.coordinator.commands.task
            await asyncio.sleep(0)
            if report_start:
                self.device_response("heat")
            self.put("binary_sensor.grid", "off")
            self.put("sensor.soc", "40", unit_of_measurement="%")
            self.coordinator._evaluate()
            release.set()
            await worker
            self.assertEqual(
                [call.args[1] for call in self.hass.services.async_call.call_args_list],
                ["set_temperature", "set_hvac_mode"],
            )
            self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "off")
            await self.coordinator.async_shutdown()

    async def test_service_timeout_is_reported_and_does_not_leave_worker_stuck(self):
        never = asyncio.Event()

        async def hang(*args, **kwargs):
            await never.wait()

        self.hass.services.async_call.side_effect = hang
        with patch.object(importlib.import_module("scm_adapter_test.runtime.commands"), "COMMAND_TIMEOUT_SECONDS", 0.001):
            with self.assertLogs("scm_adapter_test.runtime.commands", level="ERROR"):
                await self.control_mode()
        self.assertTrue(self.coordinator.data["command_failed"])
        self.assertIsNone(self.coordinator.commands.task)

    async def test_grid_energy_permission_is_independent_of_manual_pause_and_mode(self):
        self.coordinator.runtime.manual_date = dt.now().date().isoformat()
        self.put("sensor.room", "unavailable")
        for mode in ("disabled", "observation", "control"):
            await self.coordinator.async_set_mode(mode)
            self.assertTrue(self.coordinator.data["energy_allowed"])
            self.assertEqual(self.coordinator.data["energy_reason"], "grid_ready")
        self.hass.services.async_call.assert_not_called()

    async def test_grid_energy_permission_ignores_discharge_but_requires_valid_soc(self):
        self.put("sensor.soc", "40", unit_of_measurement="%")
        self.put("sensor.battery", "500", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertTrue(self.coordinator.data["energy_allowed"])
        self.assertEqual(self.coordinator.data["energy_reason"], "grid_ready")
        self.put("sensor.soc", "unavailable")
        self.coordinator._evaluate()
        self.assertFalse(self.coordinator.data["energy_allowed"])
        self.assertEqual(self.coordinator.data["energy_reason"], "invalid_energy_data")

    async def test_contextless_stop_response_does_not_pause(self):
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("binary_sensor.grid", "off")
        self.put("sensor.soc", "40", unit_of_measurement="%")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.device_response("off")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.assertFalse(self.coordinator.data["manual_pause"])
        self.assertFalse(self.coordinator.data["running"])

    async def test_low_soc_outage_during_command_is_rechecked_on_completion(self):
        async def delayed(domain, service, data, **kwargs):
            if service == "set_temperature":
                clock.current += timedelta(seconds=6)
                self.put("binary_sensor.grid", "off")
                self.put("sensor.soc", "40", unit_of_measurement="%")

        self.hass.services.async_call.side_effect = delayed
        await self.control_mode()
        self.assertEqual(
            [call.args[1] for call in self.hass.services.async_call.call_args_list],
            ["set_temperature", "set_hvac_mode"],
        )
        self.assertEqual(self.coordinator.data["energy_reason"], "low_soc")

    async def test_grid_with_98_percent_soc_keeps_running_despite_discharge(self):
        self.put("sensor.soc", "98", unit_of_measurement="%")
        self.put("sensor.battery", "500", unit_of_measurement="W")
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        for minutes in (10, 10):
            clock.current += timedelta(minutes=minutes)
            for state in self.states.values():
                state.last_reported = clock.current
            self.coordinator._evaluate()
            if self.coordinator.commands.task:
                await self.coordinator.commands.task
            self.assertEqual(self.coordinator.data["strategy_reason"], "grid_ready")
            self.assertTrue(self.coordinator.data["running"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_heating_compensates_warmer_ac_sensor(self):
        self.coordinator.settings["target_temperature"] = 22
        self.states["climate.ac"].attributes.update(
            current_temperature=25, min_temp=16, max_temp=30, target_temp_step=1
        )
        await self.control_mode()
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 27)
        self.assertEqual(self.coordinator.data["ac_temperature"], 25)
        self.assertEqual(self.coordinator.data["temperature_offset"], 5)
        self.assertEqual(self.coordinator.data["ac_target_temperature"], 27)
        self.assertEqual(self.coordinator.settings["target_temperature"], 22)

    async def test_cooling_compensation_uses_same_sensor_difference(self):
        self.coordinator.settings["hvac_mode"] = "cool"
        self.coordinator.settings["target_temperature"] = 22
        self.put("sensor.room", "26", unit_of_measurement="°C")
        self.states["climate.ac"].attributes.update(
            current_temperature=29, min_temp=16, max_temp=30, target_temp_step=1
        )
        await self.control_mode()
        self.assertEqual(
            self.hass.services.async_call.call_args.args[2],
            {
                "entity_id": "climate.ac",
                "hvac_mode": "cool",
                "temperature": 25,
            },
        )

    async def test_temperature_correction_is_limited_but_stop_is_immediate(self):
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.device_response("heat", current_temperature=25)
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.assertFalse(self.coordinator.data["manual_pause"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)
        clock.current += timedelta(seconds=60)
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 27)
        self.assertEqual(self.hass.services.async_call.await_count, 2)
        self.put("binary_sensor.grid", "off")
        self.put("sensor.soc", "40", unit_of_measurement="%")
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "off")
        self.assertEqual(self.hass.services.async_call.await_count, 3)

    async def test_missing_ac_temperature_blocks_start_and_stops_running_unit(self):
        self.states["climate.ac"].attributes["current_temperature"] = None
        await self.control_mode()
        self.hass.services.async_call.assert_not_called()
        self.assertTrue(self.coordinator.data["invalid_data"])
        self.assertIsNone(self.coordinator.data["ac_target_temperature"])
        self.put(
            "climate.ac",
            "heat",
            hvac_modes=["heat", "cool", "off"],
            temperature=23,
            current_temperature=None,
        )
        self.coordinator._evaluate()
        await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "off")

    async def test_compensated_target_clamps_to_device_range(self):
        self.coordinator.settings["ac_max_temperature"] = 32
        self.states["climate.ac"].attributes.update(
            current_temperature=35, min_temp=16, max_temp=30
        )
        await self.control_mode()
        self.assertEqual(self.coordinator.data["ac_target_temperature"], 30)
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 30)

    async def test_observation_calculates_compensation_without_commands(self):
        self.states["climate.ac"].attributes["current_temperature"] = 25
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["ac_target_temperature"], 27)
        self.hass.services.async_call.assert_not_called()

    async def test_default_command_limits_apply_to_heat_and_cool(self):
        self.states["climate.ac"].attributes["current_temperature"] = 35
        await self.control_mode()
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 27)
        await self.coordinator.async_set_mode("observation")
        self.coordinator.settings["hvac_mode"] = "cool"
        self.put("sensor.room", "30", unit_of_measurement="°C")
        self.states["climate.ac"].attributes["current_temperature"] = 15
        clock.current += timedelta(seconds=60)
        await self.control_mode()
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["temperature"], 15)

    async def test_compensation_keeps_target_until_reserve_is_below_1_1(self):
        for mode, room, target, ample, boundary, small, expected in (
            ("heat", "20", 26, 24, 24.9, 25, 27),
            ("cool", "26", 22, 24, 23.1, 23, 20),
        ):
            self.coordinator.settings["hvac_mode"] = mode
            self.put("sensor.room", room, unit_of_measurement="°C")
            for current in (ample, boundary):
                self.put("climate.ac", mode, hvac_modes=["heat", "cool", "off"],
                         temperature=target, current_temperature=current)
                self.coordinator._evaluate()
                self.assertIsNone(self.coordinator.commands._control_command(self.states["climate.ac"]))
            self.states["climate.ac"].attributes["current_temperature"] = small
            self.coordinator._evaluate()
            command = self.coordinator.commands._control_command(self.states["climate.ac"])
            self.assertEqual(command[1]["temperature"], expected)

    async def test_out_of_bounds_target_is_corrected_even_with_ample_reserve(self):
        self.put("climate.ac", "heat", hvac_modes=["heat", "off"],
                 temperature=28, current_temperature=24)
        self.coordinator._evaluate()
        command = self.coordinator.commands._control_command(self.states["climate.ac"])
        self.assertEqual(command[1]["temperature"], 27)

    async def test_capped_target_is_not_repeated_when_reserve_is_small(self):
        self.put("climate.ac", "heat", hvac_modes=["heat", "off"],
                 temperature=27, current_temperature=26)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["ac_target_temperature"], 27)
        self.assertIsNone(self.coordinator.commands._control_command(self.states["climate.ac"]))

    async def test_custom_temperature_limits_survive_reload(self):
        await self.coordinator.async_shutdown()
        self.entry.options = {"ac_min_temperature": 17, "ac_max_temperature": 25}
        self.states["climate.ac"].attributes["current_temperature"] = 30
        new = adapter.SolarClimateCoordinator(self.hass, self.entry)
        await new.async_initialize()
        self.assertEqual(new.settings["ac_min_temperature"], 17)
        self.assertEqual(new.settings["ac_max_temperature"], 25)
        self.assertEqual(new.data["ac_target_temperature"], 25)

    async def test_fahrenheit_reserve_is_compared_in_celsius(self):
        self.hass.config.units.temperature_unit = "°F"
        self.put("climate.ac", "heat", hvac_modes=["heat", "off"],
                 temperature=78.8, current_temperature=75.2)
        self.coordinator._evaluate()
        self.assertIsNone(self.coordinator.commands._control_command(self.states["climate.ac"]))
        self.states["climate.ac"].attributes["current_temperature"] = 77
        self.coordinator._evaluate()
        command = self.coordinator.commands._control_command(self.states["climate.ac"])
        self.assertEqual(command[1]["temperature"], 80.6)

    async def test_limit_metadata_is_read_automatically_and_not_aged(self):
        self.put("number.limit", "2.5", unit_of_measurement="kW")
        self.states["number.limit"].last_reported = clock.current - timedelta(days=3)
        self.coordinator.settings["grid_import_limit_entity"] = "number.limit"
        self.put("sensor.grid", "1800", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["grid_import_limit"], 2500)
        self.assertEqual(self.coordinator.data["grid_import_margin"], -200)
        self.assertFalse(self.coordinator.data["energy_allowed"])
        self.assertEqual(self.coordinator.data["energy_reason"], "grid_import_limit")
        self.put("number.limit", "3000", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertTrue(self.coordinator.data["energy_allowed"])
        self.assertEqual(self.coordinator.data["grid_import_margin"], 300)

    async def test_zero_limit_is_unlimited_without_grid_power_meter(self):
        self.put("number.limit", "0", unit_of_measurement="W")
        self.coordinator.settings["grid_import_limit_entity"] = "number.limit"
        self.coordinator.settings["grid_power_entity"] = None
        self.coordinator._evaluate()
        self.assertFalse(self.coordinator.data["grid_import_limit_active"])
        self.assertTrue(self.coordinator.data["energy_allowed"])

    async def test_low_soc_grid_charging_starts_if_limit_has_capacity(self):
        self.put("number.limit", "3000", unit_of_measurement="W")
        self.coordinator.settings["grid_import_limit_entity"] = "number.limit"
        self.put("sensor.grid", "1800", unit_of_measurement="W")
        self.put("sensor.soc", "60", unit_of_measurement="%")
        self.put("sensor.battery", "-1000", unit_of_measurement="W")
        await self.control_mode()
        self.assertTrue(self.coordinator.data["energy_allowed"])
        self.assertEqual(self.coordinator.data["grid_import_margin"], 300)
        self.assertEqual(self.hass.services.async_call.call_args.args[1], "set_temperature")

    async def test_limit_change_stops_running_ac_without_waiting_for_minimum_run(self):
        self.put("number.limit", "3000", unit_of_measurement="W")
        self.coordinator.settings["grid_import_limit_entity"] = "number.limit"
        self.put("sensor.grid", "1800", unit_of_measurement="W")
        await self.control_mode()
        self.device_response("heat")
        if self.coordinator.commands.task:
            await self.coordinator.commands.task
        self.put("number.limit", "1000", unit_of_measurement="W")
        self.coordinator._state_changed(SimpleNamespace(data={"entity_id": "number.limit"}))
        await self.coordinator.commands.task
        self.assertEqual(self.hass.services.async_call.call_args.args[2]["hvac_mode"], "off")
        self.assertEqual(self.coordinator.data["energy_reason"], "grid_import_limit")

    async def test_invalid_limit_blocks_but_old_grid_meter_remains_valid(self):
        self.coordinator.settings["grid_import_limit_entity"] = "number.limit"
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["energy_reason"], "grid_limit_unavailable")
        self.assertTrue(self.coordinator.data["energy_data_invalid"])
        self.put("number.limit", "3000", unit_of_measurement="W")
        self.states["sensor.grid"].last_reported = clock.current - timedelta(seconds=901)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["energy_reason"], "grid_ready")
        self.put("binary_sensor.grid", "off")
        self.coordinator._evaluate()
        self.assertNotEqual(self.coordinator.data["energy_reason"], "grid_power_unavailable")
