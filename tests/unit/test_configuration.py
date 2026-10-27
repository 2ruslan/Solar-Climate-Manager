"""Each setting is read from its owner; group values never leak into device storage."""

import importlib
import unittest
from dataclasses import fields

from test_groups import groups

config = importlib.import_module("scm_adapter_test.domain.configuration")


class ConfigurationTests(unittest.TestCase):
    def test_every_shared_field_comes_from_group_even_when_none(self):
        sources = groups.GroupSources(generation_forecast_entity="sensor.forecast")
        policy = groups.GroupPolicy(minimum_soc=72, restart_soc=83, grid_absence_delay=120,
                                    load_scope="excludes_all_members")
        group = groups.GroupConfig("g", "House", sources, policy)
        device = {key: "stale" for key in config.GROUP_SETTING_KEYS}
        device.update(target_temperature=23, estimated_ac_power=900, operation_mode="observation")
        view = config.SettingsView(device, group)
        for source in fields(sources):
            self.assertEqual(view[source.name], getattr(sources, source.name))
        for field in fields(policy):
            self.assertEqual(view[field.name], getattr(policy, field.name))
        self.assertEqual(view["grid_absence_minutes"], 2)
        self.assertFalse(view["load_includes_ac"])
        self.assertEqual(view["target_temperature"], 23)
        device["target_temperature"] = 24
        self.assertEqual(view["target_temperature"], 24)
        self.assertEqual(device["minimum_soc"], "stale")
        self.assertFalse(config.GROUP_SETTING_KEYS & config.device_values(device, grouped=True).keys())

    def test_unassigned_device_cannot_fall_back_to_old_energy_sources(self):
        view = config.SettingsView({"pv_power_entity": "sensor.old", "minimum_soc": 0}, grouped=True)
        self.assertIsNone(view["pv_power_entity"])
        self.assertEqual(view["minimum_soc"], 85)
