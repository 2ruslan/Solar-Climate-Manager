"""Local flow logic tests with in-memory UI boundaries, not the HA harness."""

import importlib
import types
import unittest
from types import SimpleNamespace

import test_coordinator as boundaries

module = boundaries.module


class Marker(str):
    def __new__(cls, value, **kwargs):
        return super().__new__(cls, value)


class Schema:
    def __init__(self, fields):
        self.schema = fields


class Flow:
    def __init_subclass__(cls, **kwargs):
        pass

    def async_show_menu(self, **kwargs):
        return {"type": "menu", **kwargs}

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def add_suggested_values_to_schema(self, schema, values):
        return schema


module("homeassistant.config_entries", ConfigFlow=Flow, OptionsFlowWithReload=Flow)
selector = types.ModuleType("homeassistant.helpers.selector")
selector.NumberSelectorMode = SimpleNamespace(BOX="box")
for name in ["NumberSelector", "SelectSelector", "EntitySelector", "BooleanSelector"]:
    setattr(selector, name, lambda *args: None)
for name in ["NumberSelectorConfig", "SelectSelectorConfig", "EntitySelectorConfig"]:
    setattr(selector, name, lambda **kwargs: kwargs)
module("homeassistant.helpers", selector=selector)
module("probatio", Schema=Schema, Required=Marker, Optional=Marker)
flow_module = importlib.import_module("scm_adapter_test.config_flow")


class FlowLogicTests(unittest.IsolatedAsyncioTestCase):
    put = boundaries.CoordinatorTests.put

    async def asyncSetUp(self):
        await boundaries.CoordinatorTests.asyncSetUp(self)
        self.flow = flow_module.SolarClimateOptionsFlow()
        self.flow.hass = self.hass
        self.flow.config_entry = self.entry

    async def test_menu_and_separate_advanced_form(self):
        result = await self.flow.async_step_init()
        self.assertEqual(result["menu_options"], ["sources", "comfort", "energy", "advanced"])
        advanced = await self.flow.async_step_advanced()
        self.assertIn("verification_delay", advanced["data_schema"].schema)
        energy = await self.flow.async_step_energy()
        self.assertNotIn("verification_delay", energy["data_schema"].schema)
        self.assertNotIn("enabled", energy["data_schema"].schema)
        self.assertNotIn("allow_forecast_trial", energy["data_schema"].schema)

    async def test_edit_preserves_disabled_and_other_sections(self):
        self.entry.options = {"enabled": False, "max_grid_import": 700}
        result = await self.flow.async_step_comfort(
            {
                "target_temperature": 24,
                "temperature_entity": "sensor.room",
                "hysteresis": 1,
                "hvac_mode": "heat",
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertFalse(result["data"]["enabled"])
        self.assertEqual(result["data"]["max_grid_import"], 700)
        self.assertEqual(result["data"]["pv_power_entity"], "sensor.pv")

    async def test_conditional_limits_only_when_enabled(self):
        self.flow.pending = {"allow_grid_import": False, "prioritize_charging": False}
        self.assertFalse(self.flow.limit_keys())
        self.flow.pending["allow_grid_import"] = True
        self.assertEqual(self.flow.limit_keys(), {"max_grid_import"})
        self.flow.pending["prioritize_charging"] = True
        self.assertEqual(self.flow.limit_keys(), {"max_grid_import", "charging_reserve_power"})

    async def test_source_clear_keeps_schedule_and_comfort(self):
        self.entry.options["schedule_entity"] = "schedule.day"
        self.put("schedule.day", "on")
        result = await self.flow.async_step_sources(
            {
                "load_includes_ac": True,
                "load_includes_battery_charging": False,
                "grid_on_means_available": True,
                "battery_positive": "discharge",
                "grid_positive": "import",
            }
        )
        self.assertIsNone(result["data"]["pv_power_entity"])
        self.assertEqual(result["data"]["schedule_entity"], "schedule.day")
        self.assertEqual(result["data"]["target_temperature"], 23)
