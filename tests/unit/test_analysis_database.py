"""Disk retention, size limits, source isolation and restart de-duplication."""

import importlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from test_groups import groups  # noqa: F401

dbmod = importlib.import_module("scm_adapter_test.adapters.analysis_database")
p = importlib.import_module("scm_adapter_test.domain.power_analysis")


class AnalysisDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "analysis.sqlite")
        self.db = dbmod.AnalysisDatabase(self.path)

    def read(self, query):
        with closing(sqlite3.connect(self.path)) as connection:
            return connection.execute(query).fetchall()

    def test_retention_and_physical_space_reclaimed_without_new_samples(self):
        models = {"g": ("v1", p.AdaptiveAnalysis())}
        rows = [("g", "v1", t, 300, '{"ac":null}') for t in range(0, p.RAW_RETENTION+1, 60)]
        self.db.exchange(rows, models, p.RAW_RETENTION)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 43200)
        self.assertEqual(self.read("SELECT MIN(stamp) FROM observations")[0][0], 60)
        size = Path(self.path).stat().st_size
        self.db.exchange([], models, 2*p.RAW_RETENTION+1)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 0)
        self.assertLess(Path(self.path).stat().st_size, size)
        self.assertLess(size, 32*1024*1024)

    def test_global_row_limit_and_removed_group_cleanup(self):
        models = {f"g{i}": ("v1", p.AdaptiveAnalysis()) for i in range(20)}
        rows = [(key, "v1", t, 300, '{}') for key in models for t in range(0, 36000, 60)]
        with patch.object(dbmod, "MAX_ROWS", 10000):
            self.db.exchange(rows, models, 36000)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 10000)
        self.db.exchange([], {}, 36001)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 0)

    def test_rough_estimates_from_sql_and_restart_does_not_duplicate(self):
        c = p.Conditions("heat", "auto", 21, 24)
        payload = json.dumps({"ac": asdict(c)})
        model = p.AdaptiveAnalysis()
        result = self.db.exchange([("g", "v1", t, 900, payload) for t in range(0, 600, 60)],
                                  {"g": ("v1", model)}, 600)
        self.assertEqual(model.view("ac", c, 600)["low"], 0)
        saved = p.AdaptiveAnalysis.restore(result["g"][1].stored(), 600)
        count = len(saved.evidence["ac"])
        self.db.exchange([], {"g": ("v1", saved)}, 600)
        self.assertEqual(len(saved.evidence["ac"]), count)
        self.db.exchange([], {"g": ("v2", p.AdaptiveAnalysis())}, 600)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 0)

    def test_corrupt_database_is_not_silently_replaced(self):
        Path(self.path).write_bytes(b"not a sqlite database")
        with self.assertRaises(sqlite3.DatabaseError):
            self.db.exchange([], {}, 1000)
        self.assertEqual(Path(self.path).read_bytes(), b"not a sqlite database")

    def test_payload_budget_prunes_oldest_records(self):
        rows = [("g", "v1", t, 300, '{"ac":null}') for t in range(0, 1200, 60)]
        with patch.object(dbmod, "MAX_BYTES", 1000):
            self.db.exchange(rows, {"g": ("v1", p.AdaptiveAnalysis())}, 1200)
        self.assertLessEqual(self.read("SELECT SUM(length(members)+length(group_id)+length(context)+128) FROM observations")[0][0], 1000)
        self.assertEqual(self.read("SELECT MAX(stamp) FROM observations")[0][0], 1140)

    def test_twenty_day_old_cycle_still_available_after_restart(self):
        c = p.Conditions("heat", "high", 20, 24, 7)
        payload = json.dumps({"ac": asdict(c)})
        rows = [("g", "v1", i*60, 1000 if 10 <= i < 40 else 300,
                 payload if 10 <= i < 40 else '{"ac":null}') for i in range(50)]
        model = p.AdaptiveAnalysis()
        self.db.exchange(rows, {"g": ("v1", model)}, 20*86400)
        self.assertEqual(model.view("ac", c, 20*86400)["estimate"], 700)
        restored = p.AdaptiveAnalysis.restore(model.stored(), 20*86400)
        self.db.exchange([], {"g": ("v1", restored)}, 20*86400)
        self.assertEqual(restored.view("ac", c, 20*86400)["source"], "ruptures")

    def test_later_night_background_refines_earlier_rough_samples(self):
        c = p.Conditions("heat", "auto", 21, 24, 7)
        payload = json.dumps({"ac": asdict(c)})
        model = p.AdaptiveAnalysis()
        models = {"g": ("v1", model)}
        self.db.exchange([("g", "v1", t, 1000, payload) for t in range(0, 3600, 60)], models, 3600)
        self.assertEqual(model.view("ac", c, 3600)["low"], 0)
        self.db.exchange([("g", "v1", t, 300, '{"ac":null}') for t in range(3600, 7200, 60)], models, 7200)
        c = replace(c, phase="unknown")  # History began while AC was already on.
        view = model.view("ac", c, 7200)
        self.assertGreaterEqual(view["low"], 0)
        self.assertEqual(view["estimate"], 700)
        self.assertEqual(view["source"], "ruptures")
        self.assertEqual(len(model.evidence["ac"]), 60)
        self.db.exchange([], models, 7200)
        self.assertEqual(model.view("ac", c, 7200), view)

    def test_previous_model_is_replayed_to_add_central_estimate(self):
        c = p.Conditions("heat", "auto", 21, 24, 7)
        model = p.AdaptiveAnalysis()
        models = {"g": ("v1", model)}
        payload = json.dumps({"ac": asdict(c)})
        self.db.exchange([("g", "v1", t, 300, '{"ac":null}') for t in (0, 60, 120)]
                         + [("g", "v1", 180, 1000, payload)], models, 180)
        row = model.evidence["ac"][0]
        row.pop("estimate")
        row["model_version"] = 2
        self.db.exchange([], models, 180)
        self.assertEqual(model.view("ac", c, 180)["estimate"], 700)
        self.assertEqual(len(model.evidence["ac"]), 1)
