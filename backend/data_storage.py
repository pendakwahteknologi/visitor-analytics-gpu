"""Visitor statistics persistence using SQLite.

Provides the same public API as the previous JSON-based storage but backed
by SQLite for proper transactions, indexing, and concurrent access.

On first run, automatically migrates any existing ``daily_stats.json``
into the new database.
"""

import csv
import io
import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Dict
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "365"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_stats (
    date       TEXT PRIMARY KEY,
    total_visitors INTEGER NOT NULL DEFAULT 0,
    male       INTEGER NOT NULL DEFAULT 0,
    female     INTEGER NOT NULL DEFAULT 0,
    unknown    INTEGER NOT NULL DEFAULT 0,
    children   INTEGER NOT NULL DEFAULT 0,
    teens      INTEGER NOT NULL DEFAULT 0,
    young_adults INTEGER NOT NULL DEFAULT 0,
    adults     INTEGER NOT NULL DEFAULT 0,
    seniors    INTEGER NOT NULL DEFAULT 0,
    age_unknown INTEGER NOT NULL DEFAULT 0,
    timestamp  TEXT
);
"""


class DataStorage:
    """Handle persistence of visitor statistics via SQLite."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "daily_stats.db"
        self._json_path = self.data_dir / "daily_stats.json"

        self._init_db()
        self._migrate_json()
        self.cleanup_old_data(days_to_keep=DATA_RETENTION_DAYS)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _migrate_json(self):
        """One-time migration from JSON → SQLite."""
        if not self._json_path.exists():
            return

        try:
            with open(self._json_path, "r") as f:
                data = json.load(f)

            records = data.get("daily_records", {})
            if not records:
                return

            with self._connect() as conn:
                for date_key, rec in records.items():
                    ag = rec.get("age_groups", {})
                    conn.execute(
                        """INSERT OR IGNORE INTO daily_stats
                           (date, total_visitors, male, female, unknown,
                            children, teens, young_adults, adults, seniors,
                            age_unknown, timestamp)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            date_key,
                            rec.get("total_visitors", 0),
                            rec.get("male", 0),
                            rec.get("female", 0),
                            rec.get("unknown", 0),
                            ag.get("Children", 0),
                            ag.get("Teens", 0),
                            ag.get("Young Adults", 0),
                            ag.get("Adults", 0),
                            ag.get("Seniors", 0),
                            ag.get("Unknown", 0),
                            rec.get("timestamp", ""),
                        ),
                    )

            # Rename old file so migration doesn't repeat
            migrated_path = self._json_path.with_suffix(".json.migrated")
            self._json_path.rename(migrated_path)
            logger.info(f"Migrated {len(records)} daily records from JSON → SQLite")
        except Exception as e:
            logger.error(f"JSON migration failed (will retry next start): {e}")

    def _get_timezone(self):
        tz_name = os.getenv("TZ", "UTC")
        try:
            return ZoneInfo(tz_name)
        except Exception:
            return ZoneInfo("UTC")

    def _get_now(self):
        return datetime.now(self._get_timezone())

    def _get_today_key(self) -> str:
        return self._get_now().strftime("%Y-%m-%d")

    def _empty_age_groups(self) -> Dict:
        return {
            "Children": 0,
            "Teens": 0,
            "Young Adults": 0,
            "Adults": 0,
            "Seniors": 0,
            "Unknown": 0,
        }

    def _row_to_dict(self, row) -> Dict:
        """Convert a sqlite3.Row to the public dict format."""
        if row is None:
            return {
                "total_visitors": 0,
                "male": 0,
                "female": 0,
                "unknown": 0,
                "age_groups": self._empty_age_groups(),
            }
        return {
            "total_visitors": row["total_visitors"],
            "male": row["male"],
            "female": row["female"],
            "unknown": row["unknown"],
            "age_groups": {
                "Children": row["children"],
                "Teens": row["teens"],
                "Young Adults": row["young_adults"],
                "Adults": row["adults"],
                "Seniors": row["seniors"],
                "Unknown": row["age_unknown"],
            },
        }

    def _aggregate_rows(self, rows) -> Dict:
        """Sum numeric fields across multiple rows."""
        totals = {
            "total_visitors": 0,
            "male": 0,
            "female": 0,
            "unknown": 0,
        }
        age = self._empty_age_groups()
        days_with_data = 0

        for r in rows:
            totals["total_visitors"] += r["total_visitors"]
            totals["male"] += r["male"]
            totals["female"] += r["female"]
            totals["unknown"] += r["unknown"]
            age["Children"] += r["children"]
            age["Teens"] += r["teens"]
            age["Young Adults"] += r["young_adults"]
            age["Adults"] += r["adults"]
            age["Seniors"] += r["seniors"]
            age["Unknown"] += r["age_unknown"]
            days_with_data += 1

        totals["age_groups"] = age
        totals["days_with_data"] = days_with_data
        return totals

    # ------------------------------------------------------------------
    # Public API (same interface as before)
    # ------------------------------------------------------------------

    def save_current_stats(
        self,
        total_visitors: int,
        male_count: int,
        female_count: int,
        age_groups: Dict = None,
        unknown_count: int = 0,
    ):
        """Upsert today's statistics."""
        today_key = self._get_today_key()
        ag = age_groups or {}
        ts = self._get_now().isoformat()

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO daily_stats
                   (date, total_visitors, male, female, unknown,
                    children, teens, young_adults, adults, seniors,
                    age_unknown, timestamp)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(date) DO UPDATE SET
                    total_visitors=excluded.total_visitors,
                    male=excluded.male,
                    female=excluded.female,
                    unknown=excluded.unknown,
                    children=excluded.children,
                    teens=excluded.teens,
                    young_adults=excluded.young_adults,
                    adults=excluded.adults,
                    seniors=excluded.seniors,
                    age_unknown=excluded.age_unknown,
                    timestamp=excluded.timestamp""",
                (
                    today_key,
                    total_visitors,
                    male_count,
                    female_count,
                    unknown_count,
                    ag.get("Children", 0),
                    ag.get("Teens", 0),
                    ag.get("Young Adults", 0),
                    ag.get("Adults", 0),
                    ag.get("Seniors", 0),
                    ag.get("Unknown", 0),
                    ts,
                ),
            )

    def get_today_stats(self) -> Dict:
        today_key = self._get_today_key()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM daily_stats WHERE date = ?", (today_key,)
            ).fetchone()
        return self._row_to_dict(row)

    def get_weekly_stats(self) -> Dict:
        today = self._get_now()
        week_start = today - timedelta(days=6)
        start_key = week_start.strftime("%Y-%m-%d")
        end_key = today.strftime("%Y-%m-%d")

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ?",
                (start_key, end_key),
            ).fetchall()

        result = self._aggregate_rows(rows)
        result["start_date"] = start_key
        result["end_date"] = end_key
        return result

    def get_monthly_stats(self) -> Dict:
        today = self._get_now()
        month_start = today.replace(day=1)
        start_key = month_start.strftime("%Y-%m-%d")
        end_key = today.strftime("%Y-%m-%d")

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ?",
                (start_key, end_key),
            ).fetchall()

        result = self._aggregate_rows(rows)
        result["month"] = today.strftime("%B %Y")
        result["start_date"] = start_key
        result["end_date"] = end_key
        return result

    def get_all_time_stats(self) -> Dict:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM daily_stats").fetchall()
        return self._aggregate_rows(rows)

    def get_daily_range(self, start_date: str, end_date: str) -> list[Dict]:
        """Return per-day stats as a list of dicts for the given date range."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ? ORDER BY date",
                (start_date, end_date),
            ).fetchall()
        return [{"date": r["date"], **self._row_to_dict(r)} for r in rows]

    def export_csv(self) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "date", "total_visitors", "male", "female", "unknown",
            "children", "teens", "young_adults", "adults", "seniors", "age_unknown",
        ])

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM daily_stats ORDER BY date"
            ).fetchall()

        for r in rows:
            writer.writerow([
                r["date"],
                r["total_visitors"],
                r["male"],
                r["female"],
                r["unknown"],
                r["children"],
                r["teens"],
                r["young_adults"],
                r["adults"],
                r["seniors"],
                r["age_unknown"],
            ])

        return output.getvalue()

    def reset_today(self):
        today_key = self._get_today_key()
        with self._connect() as conn:
            conn.execute("DELETE FROM daily_stats WHERE date = ?", (today_key,))

    def cleanup_old_data(self, days_to_keep: int = 365):
        cutoff = (self._get_now() - timedelta(days=days_to_keep)).strftime("%Y-%m-%d")
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM daily_stats WHERE date < ?", (cutoff,))
            if cur.rowcount:
                logger.info(f"Cleaned up {cur.rowcount} old records (before {cutoff})")
