# tests/test_person_capture_store.py
"""Unit tests for PersonCaptureStore."""

import json
import os
import time
import numpy as np
import pytest
import cv2

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from person_capture_store import PersonCaptureStore


@pytest.fixture
def store(tmp_path):
    return PersonCaptureStore(capture_dir=str(tmp_path))


def _fake_frame(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _bbox():
    return (100, 50, 200, 250)


class TestSaveCapture:
    def test_saves_jpg_and_returns_record(self, store):
        frame = _fake_frame()
        record = store.save_capture(
            frame, _bbox(),
            person_id=1, gender="Male", age=30, age_group="Adults", is_new=True
        )
        assert record is not None
        assert record["gender"] == "Male"
        assert record["person_id"] == 1
        assert record["is_new"] is True
        assert os.path.isfile(os.path.join(store.capture_dir, record["filename"]))

    def test_throttle_blocks_second_save_within_30s(self, store):
        frame = _fake_frame()
        r1 = store.save_capture(frame, _bbox(), person_id=1, gender="Male", age=30, age_group="Adults", is_new=True)
        r2 = store.save_capture(frame, _bbox(), person_id=1, gender="Male", age=30, age_group="Adults", is_new=False)
        assert r1 is not None
        assert r2 is None  # throttled

    def test_throttle_allows_after_30s(self, store):
        frame = _fake_frame()
        store._last_capture_time[1] = time.time() - 31
        r = store.save_capture(frame, _bbox(), person_id=1, gender="Female", age=25, age_group="Young Adults", is_new=False)
        assert r is not None

    def test_crop_too_small_returns_none(self, store):
        frame = _fake_frame()
        tiny_bbox = (100, 100, 110, 115)  # 10x15 px
        r = store.save_capture(frame, tiny_bbox, person_id=2, gender="Male", age=30, age_group="Adults", is_new=True)
        assert r is None

    def test_record_written_to_index(self, store):
        frame = _fake_frame()
        store.save_capture(frame, _bbox(), person_id=3, gender="Female", age=22, age_group="Young Adults", is_new=True)
        records = store.get_recent(limit=10)
        assert len(records) == 1
        assert records[0]["person_id"] == 3


class TestGetRecent:
    def test_returns_newest_first(self, store):
        frame = _fake_frame()
        for i in range(1, 4):
            store._last_capture_time.clear()
            store.save_capture(frame, _bbox(), person_id=i, gender="Male", age=30, age_group="Adults", is_new=True)
            time.sleep(0.01)
        records = store.get_recent(limit=10)
        assert records[0]["person_id"] == 3
        assert records[-1]["person_id"] == 1

    def test_respects_limit(self, store):
        frame = _fake_frame()
        for i in range(1, 6):
            store._last_capture_time.clear()
            store.save_capture(frame, _bbox(), person_id=i, gender="Male", age=30, age_group="Adults", is_new=True)
        records = store.get_recent(limit=3)
        assert len(records) == 3


class TestCleanupExpired:
    def test_deletes_old_files_and_index_entries(self, store, tmp_path):
        frame = _fake_frame()
        store.save_capture(frame, _bbox(), person_id=1, gender="Male", age=30, age_group="Adults", is_new=True)

        # Back-date the index entry
        index_path = os.path.join(store.capture_dir, "index.json")
        with open(index_path) as f:
            index = json.load(f)
        index[0]["timestamp"] -= 90000  # 25 hours ago
        with open(index_path, "w") as f:
            json.dump(index, f)

        deleted = store.cleanup_expired(max_age_seconds=86400)
        assert deleted == 1
        assert store.get_recent(limit=10) == []
