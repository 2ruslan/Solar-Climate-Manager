"""Local flow logic tests with in-memory UI boundaries, not the HA harness."""

import importlib
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import test_coordinator as boundaries

module = boundaries.module


class Marker(str):
    def __new__(cls, value, **kwargs):
        return super().__new__(cls, value)

    @property
    def schema(self):
        return str(self)


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
module("homeassistant.data_entry_flow", section=lambda schema, options: schema)
selector = types.ModuleType("homeassistant.helpers.selector")
selector.NumberSelectorMode = SimpleNamespace(BOX="box")
for name in ["NumberSelector", "SelectSelector", "EntitySelector", "BooleanSelector"]:
    setattr(selector, name, lambda *args: None)
for name in ["NumberSelectorConfig", "SelectSelectorConfig", "EntitySelectorConfig"]:
    setattr(selector, name, lambda **kwargs: kwargs)
module("homeassistant.helpers", selector=selector)
module("probatio", Schema=Schema, Required=Marker, Optional=Marker)
flow_module = importlib.import_module("scm_adapter_test.config_flow")
group_module = importlib.import_module("scm_adapter_test.group_flow")
groups = importlib.import_module("scm_adapter_test.domain.groups")


class FlowLogicTests(unittest.IsolatedAsyncioTestCase):
    put = boundaries.CoordinatorTests.put

    async def asyncSetUp(self):
        await boundaries.CoordinatorTests.asyncSetUp(self)
        self.flow = flow_module.SolarClimateOptionsFlow()
        self.flow.hass = self.hass
        self.flow.config_entry = self.entry

    async def test_outdoor_settings_validate_save_and_clear(self):
        self.put("sensor.outdoor", "-2", unit_of_measurement="°C")
        result = await self.flow.async_step_comfort({
            "outdoor_temperature_entity": "sensor.outdoor",
            "minimum_outdoor_temperature": -7,
        })
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["outdoor_temperature_entity"], "sensor.outdoor")
        self.entry.options = result["data"]
        result = await self.flow.async_step_comfort({"minimum_outdoor_temperature": -8})
        self.assertIsNone(result["data"]["outdoor_temperature_entity"])
        result = await self.flow.async_step_comfort({"minimum_outdoor_temperature": float("nan")})
        self.assertEqual(result["errors"]["base"], "invalid_outdoor_threshold")
        result = await self.flow.async_step_comfort({
            "outdoor_temperature_entity": "sensor.house",
            "minimum_outdoor_temperature": -5,
        })
        self.assertEqual(result["errors"]["base"], "invalid_temperature")

    async def new_group(self):
        self.hass.data = {}
        self.flow._registry = AsyncMock(return_value=groups.GroupRegistry())
        self.flow._group_form = lambda step, schema, values, errors=None: {
            "step_id": step, "values": values, "errors": errors or {},
        }
        return await self.flow.async_step_group_create({"name": "House", "priority": 3})

    async def test_group_creation_does_not_copy_device_settings(self):
        self.entry.options.update({
            "minimum_soc": 71, "restart_soc": 83, "grid_absence_minutes": 17,
            "battery_positive": "charge", "grid_positive": "export",
            "grid_on_means_available": False, "load_includes_battery_charging": True,
            "forecast_power_now_entity": None, "load_includes_ac": False,
            "estimated_ac_power": 1500, "target_temperature": 25,
        })
        original = dict(self.entry.options)
        form = await self.new_group()
        values = form["values"]
        self.assertIsNone(values["load_power_entity"])
        self.assertEqual(values["battery_positive"], "discharge")
        self.assertEqual(values["grid_positive"], "import")
        self.assertTrue(values["grid_on_means_available"])
        self.assertFalse(values["load_includes_battery_charging"])
        self.assertNotIn("forecast_power_now_entity", values)
        self.assertEqual(values["load_scope"], "includes_all_members")
        self.assertNotIn("estimated_ac_power", values)
        self.assertNotIn("temperature_entity", values)
        values.update(load_power_entity="sensor.house", soc_entity="sensor.soc",
                      battery_power_entity="sensor.battery", grid_available_entity="binary_sensor.grid")
        form = await self.flow.async_step_group_sources(values)
        self.assertEqual(form["values"]["minimum_soc"], 85)
        self.assertEqual(form["values"]["restart_soc"], 90)
        self.assertEqual(form["values"]["grid_absence_delay"], 600)
        self.assertEqual(self.entry.options, original)

    async def test_group_creation_honors_edits_and_does_not_restore_cleared_sources(self):
        form = await self.new_group()
        values = dict(form["values"])
        self.assertEqual(values["load_scope"], "includes_all_members")
        values.pop("soc_entity")
        form = await self.flow.async_step_group_sources(values)
        self.assertEqual(form["errors"]["base"], "incomplete_sources")
        self.assertIsNone(form["values"]["soc_entity"])
        self.assertNotIn("forecast_power_now_entity", form["values"])
        values = {**form["values"], "soc_entity": "sensor.soc", "load_scope": "excludes_all_members"}
        values.update(load_power_entity="sensor.house", battery_power_entity="sensor.battery",
                      grid_available_entity="binary_sensor.grid")
        form = await self.flow.async_step_group_sources(values)
        self.assertEqual(form["step_id"], "group_policy")
        result = []

        async def commit(change, devices):
            result.append(change(groups.GroupRegistry()))
            return {"type": "create_entry"}

        self.flow._commit = commit
        policy = {**form["values"], "minimum_soc": 72, "restart_soc": 84}
        self.assertEqual((await self.flow.async_step_group_policy(policy))["type"], "create_entry")
        group = result[0].groups[0]
        self.assertFalse(hasattr(group.sources, "forecast_power_now_entity"))
        self.assertEqual(group.policy.load_scope, "excludes_all_members")
        self.assertEqual(group.policy.minimum_soc, 72)
        self.assertEqual(group.policy.restart_soc, 84)
        self.assertEqual(result[0].membership(self.flow.device_id).group_id, group.group_id)

    async def test_group_creation_missing_sources_are_not_invented(self):
        self.entry.options.update({key: None for key in groups.SHARED_SOURCE_KEYS})
        form = await self.new_group()
        self.assertTrue(all(form["values"][key] is None for key in groups.SHARED_SOURCE_KEYS))
        result = await self.flow.async_step_group_sources(form["values"])
        self.assertEqual(result["errors"]["base"], "incomplete_sources")

    async def test_grouped_form_and_legacy_steps(self):
        result = await self.flow.async_step_init()
        self.assertEqual(list(result["data_schema"].schema),
                         ["comfort", "consumption", "settings_action"])
        self.flow.async_step_group = AsyncMock(return_value={"type": "menu"})
        advanced = await self.flow.async_step_advanced()
        self.assertEqual(advanced["type"], "menu")
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
        for key in ("minimum_soc", "restart_soc", "pv_power_entity"):
            self.assertNotIn(key, result["data"])

    async def test_grouped_save_flattens_sections_and_clears_optional_sources(self):
        await self.flow.async_step_init()
        values = self.flow.values()
        helpers = importlib.import_module("scm_adapter_test.flow_helpers")
        submitted = {
            name: {key: values[key] for key in ordered if key in values}
            for name, ordered in helpers.SETTINGS_SECTIONS.items()
        }
        submitted["solar"].pop("pv_power_entity")
        submitted["comfort"]["target_temperature"] = 24
        submitted["grid"]["grid_on_means_available"] = False
        result = await self.flow.async_step_init(submitted)
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn("pv_power_entity", result["data"])
        self.assertEqual(result["data"]["target_temperature"], 24)
        self.assertNotIn("grid_on_means_available", result["data"])
        self.assertNotIn("comfort", result["data"])
        self.assertNotIn("settings_action", result["data"])

    async def test_group_navigation_does_not_save_form_edits(self):
        await self.flow.async_step_init()
        original = dict(self.entry.options)
        self.flow.async_step_group = AsyncMock(return_value={"type": "menu"})
        result = await self.flow.async_step_init({
            "settings_action": "group", "comfort": {"target_temperature": 30},
        })
        self.assertEqual(result["type"], "menu")
        self.assertEqual(self.entry.options, original)

    async def test_conditional_limits_only_when_enabled(self):
        form = await self.flow.async_step_energy()
        self.assertEqual(
            set(form["data_schema"].schema), flow_module.ACCOUNTING_KEYS
        )

    async def test_device_energy_does_not_save_group_thresholds(self):
        for restart in (80, 85):
            result = await self.flow.async_step_energy({
                "estimated_ac_power": 900, "minimum_soc": 85, "restart_soc": restart,
            })
            self.assertNotIn("minimum_soc", result["data"])
            self.assertNotIn("restart_soc", result["data"])
        result = await self.flow.async_step_energy({
            "estimated_ac_power": 900, "minimum_soc": 85, "restart_soc": 90,
        })
        self.assertEqual(result["type"], "create_entry")

    async def test_source_clear_keeps_schedule_and_comfort(self):
        self.entry.options["schedule_entity"] = "schedule.day"
        self.put("schedule.day", "on")
        self.flow.async_step_group = AsyncMock(return_value={"type": "menu"})
        original = dict(self.entry.options)
        result = await self.flow.async_step_sources(
            {
                "load_includes_ac": True,
                "load_includes_battery_charging": False,
                "grid_on_means_available": True,
                "battery_positive": "discharge",
                "grid_positive": "import",
            }
        )
        self.assertEqual(result["type"], "menu")
        self.assertEqual(self.entry.options, original)

    async def test_out_of_range_target_rejected_by_comfort_form(self):
        self.states["climate.ac"].attributes.update(min_temp=16, max_temp=30, supported_features=1)
        result = await self.flow.async_step_comfort({"target_temperature": 35})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"]["base"], "invalid_target")

    async def test_comfort_validates_command_temperature_limits(self):
        form = await self.flow.async_step_comfort()
        self.assertIn("ac_min_temperature", form["data_schema"].schema)
        self.assertIn("ac_max_temperature", form["data_schema"].schema)
        result = await self.flow.async_step_comfort({
            "ac_min_temperature": 28, "ac_max_temperature": 27,
        })
        self.assertEqual(result["errors"]["base"], "invalid_ac_temperature_limits")
        self.states["climate.ac"].attributes.update(min_temp=16, max_temp=30)
        result = await self.flow.async_step_comfort({
            "ac_min_temperature": 10, "ac_max_temperature": 15,
        })
        self.assertEqual(result["errors"]["base"], "invalid_ac_temperature_limits")
        result = await self.flow.async_step_comfort({
            "ac_min_temperature": 17, "ac_max_temperature": 28,
        })
        self.assertEqual(result["type"], "create_entry")

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
        helpers = importlib.import_module("scm_adapter_test.flow_helpers")
        schema = flow_module.settings_schema(self.flow.values(), helpers.SOURCE_KEYS)
        self.assertIn("grid_import_limit_entity", schema.schema)

    async def test_limit_source_can_be_cleared_without_changing_comfort(self):
        self.entry.options["grid_import_limit_entity"] = "number.limit"
        self.flow.async_step_group = AsyncMock(return_value={"type": "menu"})
        result = await self.flow.async_step_sources({})
        self.assertEqual(result["type"], "menu")
        self.flow.async_step_group.assert_awaited_once()
