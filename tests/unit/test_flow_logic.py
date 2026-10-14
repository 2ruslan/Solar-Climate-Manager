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
        self.assertEqual(set(advanced["data_schema"].schema), {"grid_absence_minutes"})
        energy = await self.flow.async_step_energy()
        self.assertNotIn("verification_delay", energy["data_schema"].schema)
        self.assertNotIn("enabled", energy["data_schema"].schema)
        self.assertNotIn("allow_forecast_trial", energy["data_schema"].schema)

    async def test_edit_preserves_disabled_and_other_sections(self):
        self.entry.options = {
            "operation_mode": "disabled", "minimum_soc": 90, "restart_soc": 95,
        }
        result = await self.flow.async_step_comfort(
            {
                "target_temperature": 24,
                "temperature_entity": "sensor.room",
                "hysteresis": 1,
                "hvac_mode": "heat",
            }
        )
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["operation_mode"], "disabled")
        self.assertEqual(result["data"]["minimum_soc"], 90)
        self.assertEqual(result["data"]["restart_soc"], 95)
        self.assertEqual(result["data"]["pv_power_entity"], "sensor.pv")

    async def test_conditional_limits_only_when_enabled(self):
        form = await self.flow.async_step_energy()
        self.assertEqual(
            set(form["data_schema"].schema), {"estimated_ac_power", "minimum_soc", "restart_soc"}
        )

    async def test_energy_rejects_equal_or_reversed_soc_thresholds(self):
        for restart in (80, 85):
            result = await self.flow.async_step_energy({
                "estimated_ac_power": 900, "minimum_soc": 85, "restart_soc": restart,
            })
            self.assertEqual(result["errors"]["base"], "invalid_soc_thresholds")
        result = await self.flow.async_step_energy({
            "estimated_ac_power": 900, "minimum_soc": 85, "restart_soc": 90,
        })
        self.assertEqual(result["type"], "create_entry")

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

    async def test_out_of_range_target_rejected_by_comfort_form(self):
        self.states["climate.ac"].attributes.update(min_temp=16, max_temp=30, supported_features=1)
        result = await self.flow.async_step_comfort({"target_temperature": 35})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "invalid_target")

    async def test_unsupported_single_target_rejected_by_form(self):
        self.states["climate.ac"].attributes["supported_features"] = 0
        result = await self.flow.async_step_comfort({"target_temperature": 23})
        self.assertEqual(result["errors"]["base"], "unsupported_temperature")

    async def test_limit_source_uses_number_and_power_units(self):
        self.put("number.limit", "3", unit_of_measurement="kW")
        values = {**self.entry.data, "grid_import_limit_entity": "number.limit"}
        self.assertIsNone(flow_module.validate(self.hass, values))
        self.put("number.limit", "3", unit_of_measurement="kWh")
        self.assertEqual(flow_module.validate(self.hass, values), "invalid_power")
        self.put("sensor.limit", "3000", unit_of_measurement="W")
        self.assertEqual(
            flow_module.validate(self.hass, {**values, "grid_import_limit_entity": "sensor.limit"}),
            "invalid_energy_source",
        )
        schema = flow_module.settings_schema(self.flow.values(), flow_module.SOURCE_KEYS)
        self.assertIn("grid_import_limit_entity", schema.schema)

    async def test_limit_source_can_be_cleared_without_changing_comfort(self):
        self.entry.options["grid_import_limit_entity"] = "number.limit"
        result = await self.flow.async_step_sources({})
        self.assertEqual(result["type"], "create_entry")
        self.assertIsNone(result["data"]["grid_import_limit_entity"])
        self.assertEqual(result["data"]["target_temperature"], 23)
