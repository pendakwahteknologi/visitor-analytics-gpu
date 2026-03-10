"""Unit tests for atomic file operations."""

import json
import pytest

from atomic_write import atomic_write_json, atomic_read_json


class TestAtomicWriteRead:
    def test_round_trip(self, tmp_path):
        fp = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        atomic_write_json(fp, data)
        result = atomic_read_json(fp)
        assert result == data

    def test_read_missing_returns_default(self, tmp_path):
        fp = tmp_path / "missing.json"
        assert atomic_read_json(fp, default={"empty": True}) == {"empty": True}

    def test_read_corrupted_returns_default(self, tmp_path):
        fp = tmp_path / "corrupted.json"
        fp.write_text("{invalid json!!!")
        result = atomic_read_json(fp, default={"fallback": True})
        assert result == {"fallback": True}
        # Backup should have been created
        backups = list(tmp_path.glob("*.corrupted.*"))
        assert len(backups) == 1

    def test_overwrite_existing(self, tmp_path):
        fp = tmp_path / "overwrite.json"
        atomic_write_json(fp, {"v": 1})
        atomic_write_json(fp, {"v": 2})
        assert atomic_read_json(fp)["v"] == 2

    def test_nested_data(self, tmp_path):
        fp = tmp_path / "nested.json"
        data = {
            "a": [1, 2, {"b": True}],
            "c": {"d": [None, 3.14]},
        }
        atomic_write_json(fp, data)
        assert atomic_read_json(fp) == data

    def test_creates_parent_dirs(self, tmp_path):
        fp = tmp_path / "sub" / "dir" / "file.json"
        atomic_write_json(fp, {"ok": True})
        assert atomic_read_json(fp) == {"ok": True}
