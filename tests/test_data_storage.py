"""Unit tests for the SQLite-backed DataStorage."""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from data_storage import DataStorage


@pytest.fixture
def storage(tmp_path):
    """Create a DataStorage using a temp directory."""
    return DataStorage(data_dir=str(tmp_path))


@pytest.fixture
def populated_storage(storage):
    """Storage pre-loaded with a few days of data."""
    today = datetime.now(ZoneInfo(os.getenv("TZ", "UTC")))
    for offset in range(5):
        day = today - timedelta(days=offset)
        # Patch _get_now to simulate different days
        with patch.object(storage, "_get_now", return_value=day):
            storage.save_current_stats(
                total_visitors=10 + offset,
                male_count=5 + offset,
                female_count=4,
                age_groups={
                    "Children": 1,
                    "Teens": 2,
                    "Young Adults": 3,
                    "Adults": 2 + offset,
                    "Seniors": 1,
                    "Unknown": 1,
                },
                unknown_count=1,
            )
    return storage


class TestSaveAndRetrieve:
    def test_save_and_get_today(self, storage):
        storage.save_current_stats(
            total_visitors=42,
            male_count=20,
            female_count=18,
            age_groups={"Children": 5, "Adults": 37},
            unknown_count=4,
        )
        stats = storage.get_today_stats()
        assert stats["total_visitors"] == 42
        assert stats["male"] == 20
        assert stats["female"] == 18
        assert stats["unknown"] == 4
        assert stats["age_groups"]["Children"] == 5
        assert stats["age_groups"]["Adults"] == 37

    def test_overwrite_same_day(self, storage):
        storage.save_current_stats(10, 5, 4, unknown_count=1)
        storage.save_current_stats(20, 10, 8, unknown_count=2)
        stats = storage.get_today_stats()
        assert stats["total_visitors"] == 20  # latest value, not max

    def test_empty_day(self, storage):
        stats = storage.get_today_stats()
        assert stats["total_visitors"] == 0


class TestAggregation:
    def test_weekly_aggregates(self, populated_storage):
        weekly = populated_storage.get_weekly_stats()
        assert weekly["total_visitors"] >= 10
        assert weekly["days_with_data"] >= 1
        assert "start_date" in weekly
        assert "end_date" in weekly

    def test_monthly_aggregates(self, populated_storage):
        monthly = populated_storage.get_monthly_stats()
        assert monthly["total_visitors"] >= 10
        assert "month" in monthly

    def test_all_time_aggregates(self, populated_storage):
        alltime = populated_storage.get_all_time_stats()
        assert alltime["total_visitors"] >= 50  # 10+11+12+13+14
        assert alltime["days_with_data"] == 5


class TestResetToday:
    def test_reset_clears_today(self, storage):
        storage.save_current_stats(42, 20, 18, unknown_count=4)
        storage.reset_today()
        stats = storage.get_today_stats()
        assert stats["total_visitors"] == 0


class TestExportCSV:
    def test_csv_has_header_and_rows(self, populated_storage):
        csv_text = populated_storage.export_csv()
        lines = csv_text.strip().split("\n")
        assert len(lines) >= 6  # 1 header + 5 data rows
        assert "date" in lines[0]
        assert "total_visitors" in lines[0]


class TestCleanup:
    def test_cleanup_removes_old(self, populated_storage):
        # Keep only 2 days
        populated_storage.cleanup_old_data(days_to_keep=2)
        alltime = populated_storage.get_all_time_stats()
        assert alltime["days_with_data"] <= 3  # today + 2 days back


class TestJSONMigration:
    def test_migrates_json_to_sqlite(self, tmp_path):
        """If daily_stats.json exists, it should be ingested into SQLite."""
        import json
        from datetime import datetime

        # Use a recent date so cleanup_old_data doesn't remove it
        recent_date = datetime.now().strftime("%Y-%m-%d")

        json_path = tmp_path / "daily_stats.json"
        json_path.write_text(json.dumps({
            "daily_records": {
                recent_date: {
                    "total_visitors": 100,
                    "male": 50,
                    "female": 45,
                    "unknown": 5,
                    "age_groups": {
                        "Children": 10, "Teens": 15, "Young Adults": 30,
                        "Adults": 35, "Seniors": 5, "Unknown": 5,
                    },
                    "timestamp": f"{recent_date}T23:59:00+08:00",
                }
            },
            "last_updated": f"{recent_date}T23:59:00+08:00",
        }))

        storage = DataStorage(data_dir=str(tmp_path))
        alltime = storage.get_all_time_stats()
        assert alltime["total_visitors"] == 100
        assert alltime["age_groups"]["Young Adults"] == 30

        # JSON file should have been renamed
        assert not json_path.exists()
        assert (tmp_path / "daily_stats.json.migrated").exists()
