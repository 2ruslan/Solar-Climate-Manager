"""Disk retention, size limits, source isolation and restart de-duplication."""

import importlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

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
        rows = [("g", "v1", t, 300, '{"ac":null}') for t in range(0, 86401, 60)]
        self.db.exchange(rows, models, 86400)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 1440)
        size = Path(self.path).stat().st_size
        self.db.exchange([], models, 172801)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], 0)
        self.assertLess(Path(self.path).stat().st_size, size)
        self.assertLess(size, 32*1024*1024)

    def test_global_row_limit_and_removed_group_cleanup(self):
        models = {f"g{i}": ("v1", p.AdaptiveAnalysis()) for i in range(20)}
        rows = [(key, "v1", t, 300, '{}') for key in models for t in range(0, 36000, 60)]
        self.db.exchange(rows, models, 36000)
        self.assertEqual(self.read("SELECT COUNT(*) FROM observations")[0][0], dbmod.MAX_ROWS)
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
