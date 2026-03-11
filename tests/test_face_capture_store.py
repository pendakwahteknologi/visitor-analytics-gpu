"""Tests for FaceCaptureStore — disk I/O, throttling, cleanup, index management."""

import json
import time
import pytest
import numpy as np
from pathlib import Path


@pytest.fixture
def store(tmp_path):
    """FaceCaptureStore pointing at a temp directory."""
    from face_capture_store import FaceCaptureStore
    return FaceCaptureStore(capture_dir=str(tmp_path))


def make_frame(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def make_analysis(gender="Male", age=28, age_group="Young Adults"):
    return {
        "gender": gender,
        "age": age,
        "age_group": age_group,
        "gender_confidence": 0.9,
        "embedding": np.zeros(512),
    }


# ---------------------------------------------------------------------------
# save_capture
# ---------------------------------------------------------------------------

def test_save_capture_creates_jpg(store, tmp_path):
    frame = make_frame()
    record = store.save_capture(frame, (100, 100, 200, 200), make_analysis(), visitor_id=1, is_new_visitor=True)
    assert record is not None
    assert (tmp_path / record["filename"]).exists()
    assert record["filename"].endswith(".jpg")


def test_save_capture_returns_metadata(store):
    record = store.save_capture(make_frame(), (100, 100, 200, 200),
                                make_analysis(gender="Female", age=34, age_group="Adults"),
                                visitor_id=2, is_new_visitor=False)
    assert record["gender"] == "Female"
    assert record["age"] == 34
    assert record["age_group"] == "Adults"
    assert record["visitor_id"] == 2
    assert record["is_new_visitor"] is False
    assert "id" in record and "filename" in record and "timestamp" in record


def test_save_capture_appends_to_index(store, tmp_path):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    store._last_capture_time.clear()
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index) == 2


def test_save_capture_stores_null_visitor_id_for_unconfirmed(store, tmp_path):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    index = json.loads((tmp_path / "index.json").read_text())
    assert index[0]["visitor_id"] is None
    assert index[0]["is_new_visitor"] is False


def test_save_capture_bbox_clamped_to_frame(store, tmp_path):
    """Bbox extending beyond frame dimensions must be clamped — no crash."""
    record = store.save_capture(make_frame(h=100, w=100), (80, 80, 200, 200),
                                make_analysis(), visitor_id=None, is_new_visitor=False)
    assert record is not None
    assert (tmp_path / record["filename"]).exists()


def test_save_capture_unknown_gender_skipped(store, tmp_path):
    """Unknown gender must not be saved."""
    record = store.save_capture(make_frame(), (50, 50, 150, 150),
                                make_analysis(gender="Unknown"), visitor_id=None, is_new_visitor=False)
    assert record is None
    assert not (tmp_path / "index.json").exists()


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------

def test_throttle_blocks_same_visitor_within_30s(store):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=5, is_new_visitor=False)
    record = store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=5, is_new_visitor=False)
    assert record is None


def test_throttle_allows_same_visitor_after_30s(store):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=6, is_new_visitor=False)
    store._last_capture_time[("visitor", 6)] -= 31
    record = store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=6, is_new_visitor=False)
    assert record is not None


def test_throttle_unconfirmed_keyed_by_bbox_centre(store):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    # Same quantised centre
    record = store.save_capture(make_frame(), (52, 52, 148, 148), make_analysis(), visitor_id=None, is_new_visitor=False)
    assert record is None


# ---------------------------------------------------------------------------
# get_recent
# ---------------------------------------------------------------------------

def test_get_recent_returns_newest_first(store):
    for _ in range(5):
        store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
        store._last_capture_time.clear()
        time.sleep(0.001)
    records = store.get_recent(limit=5)
    timestamps = [r["timestamp"] for r in records]
    assert timestamps == sorted(timestamps, reverse=True)


def test_get_recent_respects_limit(store):
    for _ in range(25):
        store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
        store._last_capture_time.clear()
    assert len(store.get_recent(limit=20)) == 20


# ---------------------------------------------------------------------------
# cleanup_expired
# ---------------------------------------------------------------------------

def test_cleanup_removes_files_older_than_24h(store, tmp_path):
    record = store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    # Backdate to 25 hours ago
    index_path = tmp_path / "index.json"
    index = json.loads(index_path.read_text())
    index[0]["timestamp"] = time.time() - (25 * 3600)
    index_path.write_text(json.dumps(index))

    assert store.cleanup_expired() == 1
    assert not (tmp_path / record["filename"]).exists()
    assert len(json.loads(index_path.read_text())) == 0


def test_cleanup_keeps_files_within_24h(store, tmp_path):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    assert store.cleanup_expired() == 0
    assert len(json.loads((tmp_path / "index.json").read_text())) == 1
