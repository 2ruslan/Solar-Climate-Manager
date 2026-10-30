"""Bounded SQLite observations. Every method runs in HA's executor."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from ..domain.power_analysis import RAW_RETENTION, AdaptiveAnalysis, Conditions

MAX_ROWS = 10000
GROUP_ROWS = 2880
MAX_PAYLOAD = 2048
MAX_PAGES = 8192  # 32 MiB with 4096-byte pages; journal is transient and bounded too.


class AnalysisDatabase:
    def __init__(self, path: str):
        self.path = path

    def exchange(self, batch: list[tuple[str, str, float, float, str]],
                 models: dict[str, tuple[str, AdaptiveAnalysis]], now: float,
                 ) -> dict[str, tuple[str, AdaptiveAnalysis]]:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise ValueError("Unsupported analysis database version")
            db.execute("PRAGMA page_size=4096")
            db.execute("PRAGMA auto_vacuum=FULL")
            db.execute(f"PRAGMA max_page_count={MAX_PAGES}")
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA cache_size=-1024")
            db.execute("PRAGMA user_version=1")
            db.execute("CREATE TABLE IF NOT EXISTS observations ("
                       "group_id TEXT, context TEXT, minute INTEGER, stamp REAL, watts REAL, "
                       "members TEXT, PRIMARY KEY(group_id, minute))")
            with db:
                db.execute("DELETE FROM observations WHERE stamp < ? OR stamp > ?", (now-RAW_RETENTION, now))
                for group, context in db.execute("SELECT DISTINCT group_id, context FROM observations").fetchall():
                    if group not in models or models[group][0] != context:
                        db.execute("DELETE FROM observations WHERE group_id=? AND context=?", (group, context))
                for group, context, stamp, watts, members in batch:
                    if (group in models and models[group][0] == context and now-RAW_RETENTION <= stamp <= now
                            and len(members.encode("utf-8")) <= MAX_PAYLOAD):
                        db.execute("INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?)",
                                   (group, context, int(stamp//60), stamp, watts, members))
                for group in models:
                    db.execute("DELETE FROM observations WHERE group_id=? AND minute NOT IN "
                               "(SELECT minute FROM observations WHERE group_id=? ORDER BY minute DESC LIMIT ?)",
                               (group, group, GROUP_ROWS))
                db.execute("DELETE FROM observations WHERE rowid NOT IN "
                           "(SELECT rowid FROM observations ORDER BY stamp DESC LIMIT ?)", (MAX_ROWS,))
            for group, (context, model) in models.items():
                records = db.execute("SELECT stamp, watts, members FROM observations "
                                     "WHERE group_id=? AND context=? ORDER BY stamp", (group, context)).fetchall()
                decoded: list[tuple[float, float, dict[str, Any]]] = [
                    (stamp, watts, json.loads(members)) for stamp, watts, members in records]
                model.background = [(t, w) for t, w, m in decoded if not any(m.values())]
                for stamp, watts, readings in decoded:
                    if model.last_report is None or stamp > model.last_report:
                        model.observe(now, stamp, watts,
                                      {k: Conditions(**v) if v else None for k, v in readings.items()},
                                      True, historical=True)
                model.prune(now)
            return models
