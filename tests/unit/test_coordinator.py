"""Exercise the HA adapter locally with small in-memory event/storage boundaries."""

import importlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


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
module("homeassistant.core", callback=lambda fn: fn)
module(
    "homeassistant.const",
    Platform=SimpleNamespace(SENSOR="sensor", BINARY_SENSOR="binary_sensor", SWITCH="switch"),
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
        self.entry = SimpleNamespace(
            data=data, options={}, entry_id="test", async_on_unload=self.unload.append
        )
        self.hass = SimpleNamespace(
            states=SimpleNamespace(get=self.states.get),
            config_entries=SimpleNamespace(async_entries=lambda domain: [self.entry]),
        )
        self.coordinator = adapter.SolarClimateCoordinator(self.hass, self.entry)
        self.entry.runtime_data = self.coordinator
        await self.coordinator.async_initialize()

    def put(self, entity, state, **attributes):
        self.states[entity] = SimpleNamespace(
            state=state, attributes=attributes, last_reported=clock.current
        )

    async def test_demo_starts_without_a_services_api(self):
        self.assertEqual(self.coordinator.data["demo_action"], "wait")
        clock.current += timedelta(seconds=60)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["demo_action"], "would_start")
        self.assertTrue(self.coordinator.data["virtual_running"])
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
        self.assertEqual(new.data["demo_action"], "wait")

    async def test_signed_sources_and_stale_soc(self):
        self.coordinator.settings["battery_positive"] = "charge"
        self.put("sensor.battery", "-500", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["battery_power"], 500)
        self.assertEqual(self.coordinator.data["strategy_reason"], "battery_discharge")
        self.states["sensor.soc"].last_reported = clock.current - timedelta(seconds=901)
        self.coordinator._evaluate()
        self.assertIsNone(self.coordinator.data["soc"])
        self.assertTrue(self.coordinator.data["energy_data_invalid"])

    async def test_old_forecast_used_but_old_measurements_rejected(self):
        self.states["sensor.forecast"].last_reported = clock.current - timedelta(days=2)
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["forecast_power_now"], 2800)
        self.assertTrue(self.coordinator.data["energy_allowed"])
        self.states["sensor.pv"].last_reported = clock.current - timedelta(seconds=901)
        self.coordinator._evaluate()
        self.assertIsNone(self.coordinator.data["pv_power"])
        self.assertEqual(self.coordinator.data["strategy_reason"], "invalid_energy_data")

    async def test_removed_settings_ignored_on_existing_entry(self):
        self.entry.options = {
            "forecast_detail_entity": "sensor.missing_detail",
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
        self.assertIsNone(self.coordinator.data["forecast_power_now"])
        self.assertEqual(self.coordinator.data["strategy_reason"], "invalid_energy_data")

    async def test_configured_ac_meter_missing_is_not_silently_estimated(self):
        self.coordinator.settings["ac_power_entity"] = "sensor.ac_missing"
        self.coordinator._evaluate()
        self.assertTrue(self.coordinator.data["energy_data_invalid"])
        self.assertEqual(self.coordinator.data["strategy_reason"], "invalid_energy_data")

    async def test_inclusive_load_and_separate_charge_mapping(self):
        self.coordinator.settings["load_includes_battery_charging"] = True
        self.coordinator.settings["battery_charge_power_entity"] = "sensor.charge"
        self.put("sensor.house", "1.6", unit_of_measurement="kW")
        self.put("sensor.charge", "1000", unit_of_measurement="W")
        self.coordinator._evaluate()
        self.assertEqual(self.coordinator.data["load_power"], 1600)
        self.assertEqual(self.coordinator.data["house_load_power"], 600)
        self.assertEqual(self.coordinator.data["solar_margin"], 1000)
        self.put("sensor.charge", "unavailable")
        self.coordinator._evaluate()
        self.assertIsNone(self.coordinator.data["house_load_power"])
        self.assertTrue(self.coordinator.data["energy_data_invalid"])
