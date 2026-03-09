import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import logging
from typing import Dict, List
from zoneinfo import ZoneInfo

try:
    from .atomic_write import atomic_write_json, atomic_read_json
except ImportError:
    from atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)


class DataStorage:
    """Handle persistence of visitor statistics."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.daily_file = self.data_dir / "daily_stats.json"
        self.current_data = self._load_daily_data()

    def _load_daily_data(self) -> Dict:
        """Load daily statistics from file."""
        return atomic_read_json(self.daily_file, default=self._create_empty_data())

    def _get_timezone(self):
        """Get configured timezone."""
        tz_name = os.getenv('TZ', 'UTC')
        try:
            return ZoneInfo(tz_name)
        except:
            return ZoneInfo('UTC')
    
    def _get_now(self):
        """Get current time in configured timezone."""
        return datetime.now(self._get_timezone())

    def _create_empty_data(self) -> Dict:
        """Create empty data structure."""
        return {
            "daily_records": {},
            "last_updated": self._get_now().isoformat()
        }

    def _get_today_key(self) -> str:
        """Get today's date key."""
        return self._get_now().strftime("%Y-%m-%d")

    def save_current_stats(self, total_visitors: int, male_count: int, female_count: int, age_groups: Dict = None, unknown_count: int = 0):
        """Save current day's statistics.

        This method now KEEPS the maximum values to prevent data loss when
        session is reset. Daily records should only grow, never shrink.
        """
        today_key = self._get_today_key()

        # Get existing record for today (if any)
        existing = self.current_data["daily_records"].get(today_key, {})

        # Keep the maximum values (don't let resets erase accumulated data)
        record = {
            "date": today_key,
            "total_visitors": max(total_visitors, existing.get("total_visitors", 0)),
            "male": max(male_count, existing.get("male", 0)),
            "female": max(female_count, existing.get("female", 0)),
            "unknown": max(unknown_count, existing.get("unknown", 0)),
            "timestamp": self._get_now().isoformat()
        }

        # Add age groups if provided, keeping max values
        if age_groups:
            existing_age = existing.get("age_groups", self._empty_age_groups())
            record["age_groups"] = {}
            for group in ["Children", "Teens", "Young Adults", "Adults", "Seniors", "Unknown"]:
                record["age_groups"][group] = max(
                    age_groups.get(group, 0),
                    existing_age.get(group, 0)
                )
        elif "age_groups" in existing:
            record["age_groups"] = existing["age_groups"]

        self.current_data["daily_records"][today_key] = record
        self.current_data["last_updated"] = self._get_now().isoformat()

        self._save_to_file()

    def _save_to_file(self):
        """Save data to JSON file."""
        try:
            atomic_write_json(self.daily_file, self.current_data, indent=2)
        except Exception as e:
            logger.error(f"Error saving data: {e}")

    def _empty_age_groups(self) -> Dict:
        """Return empty age groups structure."""
        return {
            "Children": 0,
            "Teens": 0,
            "Young Adults": 0,
            "Adults": 0,
            "Seniors": 0,
            "Unknown": 0
        }

    def get_today_stats(self) -> Dict:
        """Get today's statistics."""
        today_key = self._get_today_key()
        default = {
            "total_visitors": 0,
            "male": 0,
            "female": 0,
            "unknown": 0,
            "age_groups": self._empty_age_groups()
        }
        record = self.current_data["daily_records"].get(today_key, default)
        # Ensure all fields exist
        if "age_groups" not in record:
            record["age_groups"] = self._empty_age_groups()
        if "unknown" not in record:
            record["unknown"] = 0
        return record

    def get_weekly_stats(self) -> Dict:
        """Get this week's statistics (last 7 days)."""
        today = self._get_now()
        week_start = today - timedelta(days=6)  # Last 7 days including today

        total_visitors = 0
        male = 0
        female = 0
        unknown = 0
        days_with_data = 0
        age_groups = self._empty_age_groups()

        for i in range(7):
            date_key = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
            if date_key in self.current_data["daily_records"]:
                day_data = self.current_data["daily_records"][date_key]
                total_visitors += day_data.get("total_visitors", 0)
                male += day_data.get("male", 0)
                female += day_data.get("female", 0)
                unknown += day_data.get("unknown", 0)
                days_with_data += 1

                # Aggregate age groups
                day_age_groups = day_data.get("age_groups", {})
                for group, count in day_age_groups.items():
                    if group in age_groups:
                        age_groups[group] += count

        return {
            "total_visitors": total_visitors,
            "male": male,
            "female": female,
            "unknown": unknown,
            "age_groups": age_groups,
            "days_with_data": days_with_data,
            "start_date": week_start.strftime("%Y-%m-%d"),
            "end_date": today.strftime("%Y-%m-%d")
        }

    def get_monthly_stats(self) -> Dict:
        """Get this month's statistics."""
        today = self._get_now()
        month_start = today.replace(day=1)

        total_visitors = 0
        male = 0
        female = 0
        unknown = 0
        days_with_data = 0
        age_groups = self._empty_age_groups()

        # Iterate through all days in current month
        current_date = month_start
        while current_date.month == today.month:
            date_key = current_date.strftime("%Y-%m-%d")
            if date_key in self.current_data["daily_records"]:
                day_data = self.current_data["daily_records"][date_key]
                total_visitors += day_data.get("total_visitors", 0)
                male += day_data.get("male", 0)
                female += day_data.get("female", 0)
                unknown += day_data.get("unknown", 0)
                days_with_data += 1

                # Aggregate age groups
                day_age_groups = day_data.get("age_groups", {})
                for group, count in day_age_groups.items():
                    if group in age_groups:
                        age_groups[group] += count

            current_date += timedelta(days=1)
            if current_date > today:
                break

        return {
            "total_visitors": total_visitors,
            "male": male,
            "female": female,
            "unknown": unknown,
            "age_groups": age_groups,
            "days_with_data": days_with_data,
            "month": today.strftime("%B %Y"),
            "start_date": month_start.strftime("%Y-%m-%d"),
            "end_date": today.strftime("%Y-%m-%d")
        }

    def get_all_time_stats(self) -> Dict:
        """Get all-time statistics."""
        total_visitors = 0
        male = 0
        female = 0
        unknown = 0
        days_with_data = len(self.current_data["daily_records"])
        age_groups = self._empty_age_groups()

        for day_data in self.current_data["daily_records"].values():
            total_visitors += day_data.get("total_visitors", 0)
            male += day_data.get("male", 0)
            female += day_data.get("female", 0)
            unknown += day_data.get("unknown", 0)

            # Aggregate age groups
            day_age_groups = day_data.get("age_groups", {})
            for group, count in day_age_groups.items():
                if group in age_groups:
                    age_groups[group] += count

        return {
            "total_visitors": total_visitors,
            "male": male,
            "female": female,
            "unknown": unknown,
            "age_groups": age_groups,
            "days_with_data": days_with_data
        }

    def reset_today(self):
        """Reset today's statistics."""
        today_key = self._get_today_key()
        if today_key in self.current_data["daily_records"]:
            del self.current_data["daily_records"][today_key]
            self._save_to_file()

    def cleanup_old_data(self, days_to_keep: int = 90):
        """Remove data older than specified days."""
        cutoff_date = self._get_now() - timedelta(days=days_to_keep)
        cutoff_key = cutoff_date.strftime("%Y-%m-%d")

        keys_to_remove = [
            key for key in self.current_data["daily_records"].keys()
            if key < cutoff_key
        ]

        for key in keys_to_remove:
            del self.current_data["daily_records"][key]

        if keys_to_remove:
            self._save_to_file()
            logger.info(f"Cleaned up {len(keys_to_remove)} old records")
