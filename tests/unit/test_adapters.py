"""Regression tests for capture, normalization and the existing persistence format."""

import importlib
import json
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from test_coordinator import constants

sources = importlib.import_module("scm_adapter_test.adapters.sources")
storage = importlib.import_module("scm_adapter_test.adapters.storage")
models = importlib.import_module("scm_adapter_test.domain.types")
presentation = importlib.import_module("scm_adapter_test.presentation")


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
        self.settings = {
            **constants.DEFAULTS,
            "climate_entity": "climate.ac", "temperature_entity": "sensor.room",
            "pv_power_entity": "sensor.pv", "load_power_entity": "sensor.load",
            "battery_power_entity": "sensor.battery", "grid_power_entity": "sensor.grid",
            "soc_entity": "sensor.soc", "grid_available_entity": "binary_sensor.grid",
            "forecast_power_now_entity": "sensor.forecast",
            "forecast_power_30m_entity": "sensor.forecast",
            "forecast_power_60m_entity": "sensor.forecast",
        }
        self.states = {}
        self.put("climate.ac", "off", current_temperature=21, temperature=23,
                 hvac_modes=["heat", "cool", "off"])
        self.put("sensor.room", "20", unit_of_measurement="°C")
        for name, value, unit in (
            ("pv", "2.8", "kW"), ("load", "600", "W"), ("battery", "0", "W"),
            ("grid", "0", "W"), ("soc", "95", "%"), ("forecast", "2800", "W"),
        ):
            self.put(f"sensor.{name}", value, unit_of_measurement=unit)
        self.put("binary_sensor.grid", "on")

    def put(self, entity, state, **attributes):
        self.states[entity] = SimpleNamespace(
            state=state, attributes=attributes, last_reported=self.now,
        )

    def capture(self, get_state=None, unit="°C"):
        return sources.read_sources(
            get_state or self.states.get, self.settings,
            models.DeviceConfig.from_settings(self.settings), unit, self.now,
        )

    def test_shared_sources_read_once_and_snapshot_is_detached(self):
        get_state = Mock(side_effect=self.states.get)
        snapshot = self.capture(get_state)
        counts = Counter(call.args[0] for call in get_state.call_args_list)
        self.assertEqual(set(counts.values()), {1})
        self.assertNotIn("sensor.forecast", counts)
        self.assertEqual(snapshot.captured_at, self.now)
        self.assertEqual(snapshot.readings["pv_power_entity"].reported_at, self.now)
        self.states["sensor.pv"].state = "100"
        self.assertEqual(snapshot.energy.pv, 2800)
        with self.assertRaises(TypeError):
            snapshot.values["pv_power"] = 100
        with self.assertRaises(TypeError):
            snapshot.readings["pv_power_entity"] = None

    def test_measurement_values_are_validated_without_report_age(self):
        cases = [
            ("missing", None, None, None),
            ("unavailable", "unavailable", "W", self.now),
            ("valid", "100", "W", self.now - timedelta(seconds=901)),
            ("valid", "100", "W", self.now + timedelta(seconds=1)),
            ("invalid", "100", "kWh", self.now),
            ("valid", "0", "W", self.now - timedelta(seconds=900)),
        ]
        for status, value, unit, reported in cases:
            with self.subTest(status=status):
                if value is None:
                    self.states.pop("sensor.pv", None)
                else:
                    self.put("sensor.pv", value, unit_of_measurement=unit)
                    self.states["sensor.pv"].last_reported = reported
                snapshot = self.capture()
                reading = snapshot.readings["pv_power_entity"]
                self.assertEqual(reading.status, status)
                self.assertEqual(reading.reported_at, reported)
                self.assertEqual(snapshot.energy.pv, float(value) if status == "valid" else None)
        self.settings.pop("pv_power_entity")
        self.assertEqual(self.capture().readings["pv_power_entity"].status, "not_configured")

    def test_energy_measurements_do_not_expire_even_with_saved_age_limit(self):
        expected = self.capture().energy
        self.settings["power_max_data_age"] = 1
        for state in self.states.values():
            state.last_reported = self.now - timedelta(days=365)
        snapshot = self.capture()
        self.assertEqual(snapshot.energy, expected)
        for key in ("pv_power_entity", "load_power_entity", "battery_power_entity",
                    "grid_power_entity", "soc_entity"):
            self.assertEqual(snapshot.readings[key].status, "valid")

    def test_temperature_schedule_and_limit_do_not_expire(self):
        self.settings.update(schedule_entity="schedule.room", grid_import_limit_entity="number.limit")
        self.put("schedule.room", "on")
        self.put("number.limit", "3", unit_of_measurement="kW")
        for key in ("sensor.room", "sensor.forecast", "schedule.room", "number.limit"):
            self.states[key].last_reported = self.now - timedelta(days=2)
        snapshot = self.capture()
        for key in ("temperature_entity",
                    "schedule_entity", "grid_import_limit_entity"):
            self.assertEqual(snapshot.readings[key].status, "valid")
        self.assertEqual(snapshot.temperature, 20)
        self.assertTrue(snapshot.energy.schedule_allowed)
        self.assertEqual(snapshot.energy.grid_import_limit, 3000)

    def test_grid_availability_ignores_report_age_and_legacy_limit(self):
        self.settings["grid_max_data_age"] = 0
        for reported in (self.now - timedelta(days=365), self.now + timedelta(days=1)):
            for state in ("on", "off"):
                for on_means_available in (True, False):
                    with self.subTest(reported=reported, state=state, polarity=on_means_available):
                        self.put("binary_sensor.grid", state)
                        self.states["binary_sensor.grid"].last_reported = reported
                        self.settings["grid_on_means_available"] = on_means_available
                        snapshot = self.capture()
                        self.assertEqual(snapshot.energy.grid, (state == "on") == on_means_available)
                        self.assertEqual(snapshot.readings["grid_available_entity"].status, "valid")
        for state in ("unknown", "unavailable", "invalid"):
            self.put("binary_sensor.grid", state)
            self.assertIsNone(self.capture().energy.grid)
        self.states.pop("binary_sensor.grid")
        self.assertIsNone(self.capture().energy.grid)

    def test_units_signs_and_charging_are_normalized_once(self):
        self.settings.update(battery_positive="charge", grid_positive="export",
                             load_includes_battery_charging=True)
        self.put("sensor.battery", "1", unit_of_measurement="kW")
        self.put("sensor.load", "1.6", unit_of_measurement="kW")
        self.put("sensor.grid", "0.5", unit_of_measurement="kW")
        self.put("sensor.room", "68", unit_of_measurement="°F")
        self.states["climate.ac"].attributes.update(current_temperature=69.8, temperature=73.4)
        snapshot = self.capture(unit="°F")
        self.assertEqual(snapshot.temperature, 20)
        self.assertAlmostEqual(snapshot.ac_temperature, 21)
        self.assertAlmostEqual(snapshot.ac_set_temperature, 23)
        self.assertEqual(snapshot.energy.battery, -1000)
        self.assertEqual(snapshot.energy.grid_power, -500)
        self.assertEqual(snapshot.values["house_load_power"], 600)
        self.assertEqual(snapshot.readings["battery_power_entity"].value, -1000)

    def test_missing_configured_ac_meter_does_not_become_a_valid_estimate(self):
        self.settings["ac_power_entity"] = "sensor.ac"
        self.states["climate.ac"].attributes["hvac_action"] = "heating"
        snapshot = self.capture()
        self.assertFalse(snapshot.energy.ac_power_valid)
        self.assertEqual(snapshot.readings["ac_power_entity"].status, "missing")
        self.assertIsNone(snapshot.values["ac_power"])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            **constants.DEFAULTS,
            "climate_entity": "climate.ac", "temperature_entity": "sensor.room",
        }
        self.saved = storage.stored_state(
            demand=True, signature=storage.demand_signature(self.settings),
            manual_date="2026-10-15", observed=models.ObservedDeviceState(True, 100, 50),
            policy=models.PolicyState(soc_blocked=True, deficit_since=150),
            policy_signature=self.settings,
        )

    def test_round_trip_keeps_cycle_and_hysteresis_but_requalifies_continuity(self):
        restored = storage.restore_runtime(self.saved, settings=self.settings, options={}, now=200)
        self.assertTrue(restored.demand)
        self.assertEqual(restored.observed, models.ObservedDeviceState(True, 100, 50))
        self.assertTrue(restored.policy.soc_blocked)
        self.assertIsNone(restored.policy.deficit_since)
        self.assertEqual(restored.manual_date, "2026-10-15")
        self.assertEqual(set(self.saved), {
            "demand", "signature", "manual_date", "control", "policy_signature",
        })

    def test_changed_settings_reset_demand_and_retain_soc_and_off_protection(self):
        changed = {**self.settings, "target_temperature": 24}
        restored = storage.restore_runtime(self.saved, settings=changed, options={}, now=200)
        self.assertFalse(restored.demand)
        self.assertTrue(restored.policy.soc_blocked)
        self.assertFalse(restored.observed.running)
        self.assertEqual(restored.observed.last_stop, 200)

    def test_pre_learning_settings_preserve_cycle_deadlines(self):
        for key in ("power_learning_enabled", "power_learning_generation"):
            self.saved["policy_signature"].pop(key)
        restored = storage.restore_runtime(self.saved, settings=self.settings, options={}, now=200)
        self.assertEqual(restored.observed, models.ObservedDeviceState(True, 100, 50))
        self.assertEqual(self.saved["policy_signature"]["target_temperature"], 23)

    def test_retired_power_settings_preserve_observed_cycle(self):
        self.saved["policy_signature"].update(power_margin_percent=20, power_max_data_age=900)
        restored = storage.restore_runtime(self.saved, settings=self.settings, options={}, now=200)
        self.assertEqual(restored.observed, models.ObservedDeviceState(True, 100, 50))

    def test_legacy_upgrade_preserves_observed_cycle_without_enabling_estimation(self):
        for key in ("power_accounting", "power_settle_seconds"):
            self.saved["policy_signature"].pop(key)
        restored = storage.restore_runtime(self.saved, settings=self.settings, options={}, now=200)
        self.assertEqual(restored.observed, models.ObservedDeviceState(True, 100, 50))
        self.assertEqual(self.settings["power_accounting"], "legacy")
        self.assertNotIn("power_accounting", self.saved["policy_signature"])
        changed = storage.restore_runtime(self.saved,
            settings={**self.settings, "power_accounting": "estimated"}, options={}, now=200)
        self.assertEqual(changed.observed.last_stop, 200)

    def test_temporary_block_options_take_precedence_and_missing_mode_is_conservative(self):
        blocked = {**self.settings, "operation_mode": "temporary_block"}
        for mode, expected in (("control", "control"), ("invalid", "observation")):
            result = storage.restore_runtime(
                self.saved, settings=blocked,
                options={"temporary_block_date": "2026-10-16", "temporary_previous_mode": mode},
                now=200,
            )
            self.assertEqual(result.manual_date, "2026-10-16")
            self.assertEqual(result.previous_mode, expected)

    def test_export_does_not_include_source_identifiers(self):
        exported = presentation.build_export(self.settings, {"temperature": 20}, None, None)
        encoded = json.dumps(exported)
        self.assertNotIn("climate.ac", encoded)
        self.assertNotIn("sensor.room", encoded)
        self.assertEqual(set(exported), {
            "version", "settings", "decision", "manual_until_date", "mode_after_temporary_block",
        })
