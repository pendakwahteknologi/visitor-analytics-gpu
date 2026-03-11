# Body Re-ID Unique Visitor Tracking — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OSNet body re-identification as the primary unique visitor counter, with a Person Captures panel showing body crop tiles above the Face Captures panel.

**Architecture:** A new `BodyReIDTracker` (in `detection.py`) replaces `VisitorTracker` as the authoritative source for `total_visitors`. `OSNetAnalyzer` extracts 512-dim body embeddings per person per analysis frame. `PersonCaptureStore` saves body crops to disk with 24h rolling storage. The frontend gains a Person Captures tile panel above the existing Face Captures panel.

**Tech Stack:** Python/FastAPI backend, OSNet-x1.0 via torchreid, OpenCV for crop/letterbox, vanilla JS + CSS frontend.

**Spec:** `docs/superpowers/specs/2026-03-11-body-reid-unique-visitor-tracking-design.md`

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| Create | `backend/person_capture_store.py` | Body crop disk storage, 24h index, throttle |
| Create | `tests/test_person_capture_store.py` | Unit tests for PersonCaptureStore |
| Modify | `backend/detection.py` | Add OSNetAnalyzer, BodyReIDTracker; retire VisitorTracker from DetectionEngine |
| Keep | `tests/test_visitor_tracker.py` | Left as-is — `VisitorTracker` class remains in detection.py |
| Create | `tests/test_body_reid_tracker.py` | Unit tests for BodyReIDTracker |
| Modify | `backend/visitor_state.py` | New save_state/restore_state signatures for BodyReIDTracker |
| Modify | `tests/test_visitor_state.py` | Update tests for new persistence API |
| Modify | `backend/streaming.py` | Wire OSNetAnalyzer, BodyReIDTracker, PersonCaptureStore |
| Modify | `backend/main.py` | /persons endpoints, shutdown handlers, health, cleanup task |
| Modify | `requirements.txt` | Add torchreid |
| Modify | `frontend/index.html` | Person Captures panel HTML above Face Captures |
| Modify | `static/css/style.css` | Person Captures panel styles |
| Modify | `static/js/app.js` | Person Captures tile logic, WS handler, page-load restore |

---

## Chunk 1: PersonCaptureStore

### Task 1: Create `PersonCaptureStore`

**Files:**
- Create: `backend/person_capture_store.py`
- Create: `tests/test_person_capture_store.py`

- [ ] **Step 1: Write failing tests first**

```python
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
```

- [ ] **Step 2: Run tests — confirm they fail with ImportError**

```bash
cd /home/adilhidayat/visitor-analytics
source venv/bin/activate
pytest tests/test_person_capture_store.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'person_capture_store'`

- [ ] **Step 3: Create `backend/person_capture_store.py`**

```python
"""Person capture storage: save body crops to disk, manage 24h index, throttle duplicates."""

import cv2
import json
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85
THROTTLE_SECONDS = 30
MIN_CROP_SIZE = 32  # px minimum dimension


class PersonCaptureStore:
    """Save body crop images to disk and maintain a 24-hour rolling index."""

    def __init__(self, capture_dir: str):
        self.capture_dir = capture_dir
        os.makedirs(capture_dir, exist_ok=True)
        self._index_path = os.path.join(capture_dir, "index.json")
        self._last_capture_time: Dict[int, float] = {}  # keyed by person_id

    def save_capture(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        person_id: int,
        gender: Optional[str],
        age: Optional[int],
        age_group: Optional[str],
        is_new: bool,
    ) -> Optional[dict]:
        """Crop body, save to disk and index. Returns metadata record or None."""
        now = time.time()
        if now - self._last_capture_time.get(person_id, 0) < THROTTLE_SECONDS:
            return None

        crop = self._crop_frame(frame, bbox)
        if crop is None:
            return None

        capture_id = f"{int(now * 1000)}_{uuid.uuid4().hex[:4]}"
        filename = f"{capture_id}.jpg"
        filepath = os.path.join(self.capture_dir, filename)

        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            logger.warning("Failed to encode body crop %s", capture_id)
            return None

        tmp_filepath = filepath + ".tmp"
        with open(tmp_filepath, "wb") as f:
            f.write(buf.tobytes())
        os.replace(tmp_filepath, filepath)
        self._last_capture_time[person_id] = now

        record = {
            "id": capture_id,
            "filename": filename,
            "timestamp": now,
            "gender": gender,
            "age": age,
            "age_group": age_group or "Unknown",
            "person_id": person_id,
            "is_new": is_new,
        }
        self._append_index(record)
        return record

    def get_recent(self, limit: int = 20) -> List[dict]:
        """Return up to `limit` records, newest first."""
        index = self._load_index()
        index.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return index[:limit]

    def cleanup_expired(self, max_age_seconds: float = 86400) -> int:
        """Delete files and index entries older than max_age_seconds. Returns count deleted."""
        now = time.time()
        index = self._load_index()
        kept, deleted_count = [], 0

        for record in index:
            if now - record.get("timestamp", 0) >= max_age_seconds:
                try:
                    safe_filename = os.path.basename(record["filename"])
                    os.remove(os.path.join(self.capture_dir, safe_filename))
                except FileNotFoundError:
                    pass
                deleted_count += 1
            else:
                kept.append(record)

        if deleted_count:
            self._write_index(kept)

        return deleted_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _crop_frame(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if (x2 - x1) < MIN_CROP_SIZE or (y2 - y1) < MIN_CROP_SIZE:
            return None
        return frame[y1:y2, x1:x2]

    def _load_index(self) -> List[dict]:
        try:
            with open(self._index_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _append_index(self, record: dict) -> None:
        index = self._load_index()
        index.append(record)
        self._write_index(index)

    def _write_index(self, index: List[dict]) -> None:
        tmp = self._index_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(index, f)
        os.replace(tmp, self._index_path)
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_person_capture_store.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/person_capture_store.py tests/test_person_capture_store.py
git commit -m "feat: add PersonCaptureStore for body crop storage"
```

---

## Chunk 2: BodyReIDTracker

### Task 2: Add `BodyReIDTracker` to `detection.py`

**Files:**
- Modify: `backend/detection.py` (append new class after line ~865)
- Create: `tests/test_body_reid_tracker.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_body_reid_tracker.py
"""Unit tests for BodyReIDTracker."""

import time
import uuid
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from detection import BodyReIDTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rand_emb(dim=512) -> np.ndarray:
    v = np.random.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-10)


def _similar_emb(base: np.ndarray, noise: float = 0.03) -> np.ndarray:
    v = base + np.random.randn(*base.shape).astype(np.float32) * noise
    return v / (np.linalg.norm(v) + 1e-10)


def _different_emb(base: np.ndarray) -> np.ndarray:
    """Return an embedding guaranteed to be dissimilar to base."""
    v = -base + np.random.randn(*base.shape).astype(np.float32) * 0.1
    return v / (np.linalg.norm(v) + 1e-10)


@pytest.fixture
def tracker():
    with patch("detection.VisitorStatePersistence") as MockPersist:
        mock = MockPersist.return_value
        mock.restore_state.return_value = (
            {},   # persons
            {},   # pending
            {"total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
             "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0,
                            "Adults": 0, "Seniors": 0, "Unknown": 0}},
            1,    # next_person_id
        )
        mock.save_state.return_value = None
        t = BodyReIDTracker(
            match_threshold=0.60,
            pending_threshold=0.55,
            confirmation_count=3,
            pending_timeout=30.0,
        )
        yield t


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------

class TestConfirmation:
    def test_three_detections_confirm_new_person(self, tracker):
        emb = _rand_emb()
        r1 = tracker.check_person(_similar_emb(emb))
        r2 = tracker.check_person(_similar_emb(emb))
        r3 = tracker.check_person(_similar_emb(emb))
        assert r1 == (False, None)
        assert r2 == (False, None)
        confirmed, pid = r3
        assert confirmed is True
        assert pid == 1

    def test_total_visitors_increments_on_confirmation(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))
        assert tracker.stats["total_visitors"] == 1

    def test_total_visitors_does_not_double_count(self, tracker):
        emb = _rand_emb()
        for _ in range(6):  # seen 6 times
            tracker.check_person(_similar_emb(emb))
        assert tracker.stats["total_visitors"] == 1

    def test_different_persons_counted_separately(self, tracker):
        e1 = _rand_emb()
        e2 = _different_emb(e1)
        for _ in range(3):
            tracker.check_person(_similar_emb(e1))
        for _ in range(3):
            tracker.check_person(_similar_emb(e2))
        assert tracker.stats["total_visitors"] == 2


# ---------------------------------------------------------------------------
# Gender attribution
# ---------------------------------------------------------------------------

class TestGenderAttribution:
    def test_gender_accumulated_during_pending_applied_on_confirmation(self, tracker):
        emb = _rand_emb()
        tracker.check_person(_similar_emb(emb), gender="Male", age=30, age_group="Adults")
        tracker.check_person(_similar_emb(emb), gender="Male", age=31, age_group="Adults")
        tracker.check_person(_similar_emb(emb), gender="Male", age=32, age_group="Adults")
        assert tracker.stats["male"] == 1
        assert tracker.stats["unknown"] == 0

    def test_attach_gender_updates_stats(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))
        assert tracker.stats["unknown"] == 1
        # Now identify gender
        tracker.attach_gender(1, "Female", age=25, age_group="Young Adults")
        assert tracker.stats["female"] == 1
        assert tracker.stats["unknown"] == 0

    def test_attach_gender_does_not_double_count(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))
        tracker.attach_gender(1, "Male", age=30, age_group="Adults")
        tracker.attach_gender(1, "Male", age=31, age_group="Adults")  # second call ignored
        assert tracker.stats["male"] == 1
        assert tracker.stats["total_visitors"] == 1


# ---------------------------------------------------------------------------
# Re-identification
# ---------------------------------------------------------------------------

class TestReIdentification:
    def test_confirmed_person_recognised_on_return(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))
        # Person leaves and returns
        is_new, pid = tracker.check_person(_similar_emb(emb))
        assert is_new is False
        assert pid == 1
        assert tracker.stats["total_visitors"] == 1  # still 1, not 2


# ---------------------------------------------------------------------------
# Pending timeout
# ---------------------------------------------------------------------------

class TestPendingTimeout:
    def test_expired_pending_dropped(self, tracker):
        emb = _rand_emb()
        tracker.check_person(_similar_emb(emb))  # creates pending
        assert len(tracker.pending) == 1

        # Expire it
        for key in tracker.pending:
            tracker.pending[key]["timestamp"] -= 31

        tracker.check_person(_rand_emb())  # triggers eviction
        assert len(tracker.pending) == 1  # only the new one


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------

class TestLRUEviction:
    def test_evicts_oldest_when_at_capacity(self, tracker):
        tracker.MAX_ACTIVE_PERSONS = 3
        embs = [_rand_emb() for _ in range(4)]
        for i, e in enumerate(embs[:3]):
            for _ in range(3):
                tracker.check_person(_similar_emb(e))
            # space out timestamps so LRU is predictable
            for pid in tracker.persons:
                tracker.persons[pid]["timestamp"] = time.time() - (len(embs) - i) * 100

        # Add 4th person — should evict oldest
        for _ in range(3):
            tracker.check_person(_similar_emb(embs[3]))
        assert len(tracker.persons) <= tracker.MAX_ACTIVE_PERSONS


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_all_state(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))
        assert tracker.stats["total_visitors"] == 1

        tracker.reset()
        assert tracker.stats["total_visitors"] == 0
        assert tracker.stats["male"] == 0
        assert len(tracker.persons) == 0
        assert len(tracker.pending) == 0
        assert tracker.next_person_id == 1


# ---------------------------------------------------------------------------
# Count-only mode
# ---------------------------------------------------------------------------

class TestCountOnlyMode:
    def test_count_only_mode_counts_immediately(self, tracker):
        """When body_embedding is None, person is counted immediately without confirmation."""
        is_new, pid = tracker.check_person(None, gender="Male", age=30, age_group="Adults")
        assert is_new is True
        assert pid == 1
        assert tracker.stats["total_visitors"] == 1
        assert tracker.stats["male"] == 1
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_body_reid_tracker.py -v 2>&1 | head -20
```

Expected: `ImportError` — `BodyReIDTracker` doesn't exist yet

- [ ] **Step 3: Add `BodyReIDTracker` class to `backend/detection.py`**

Add this import at the top of `detection.py` (after existing imports):

```python
import uuid
from collections import Counter
```

Then append this class after the `VisitorTracker` class (before `DetectionEngine`):

```python
class BodyReIDTracker:
    """Primary unique person counter using OSNet body embeddings.

    Uses body appearance Re-ID as the authoritative unique person count.
    Gender/age are optional enrichment — attributed when InsightFace succeeds.
    Falls back to count-only mode when OSNet is unavailable.
    """

    MAX_ACTIVE_PERSONS = 500

    def __init__(
        self,
        match_threshold: float = 0.60,
        pending_threshold: float = 0.55,
        memory_duration: int = 1800,
        confirmation_count: int = 3,
        pending_timeout: float = 30.0,
    ):
        self.match_threshold = match_threshold
        self.pending_threshold = pending_threshold
        self.memory_duration = memory_duration
        self.confirmation_count = confirmation_count
        self.pending_timeout = pending_timeout

        self.persons: Dict[int, dict] = {}
        self.pending: Dict[str, dict] = {}
        self.next_person_id: int = 1
        self.stats: Dict = {
            "total_visitors": 0,
            "male": 0,
            "female": 0,
            "unknown": 0,
            "age_groups": {
                "Children": 0, "Teens": 0, "Young Adults": 0,
                "Adults": 0, "Seniors": 0, "Unknown": 0,
            },
        }

        self.state_persistence = VisitorStatePersistence()
        self._restore_state()
        self.last_save_time = time.time()
        logger.info(
            "BodyReIDTracker initialized: threshold=%.2f, confirmations=%d",
            match_threshold, confirmation_count,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_person(
        self,
        body_embedding: Optional[np.ndarray],
        gender: Optional[str] = None,
        age: Optional[int] = None,
        age_group: Optional[str] = None,
    ) -> Tuple[bool, Optional[int]]:
        """Check if this body embedding is a new or known person.

        Returns:
            (True, person_id)  — just confirmed as new unique person
            (False, person_id) — known confirmed person seen again
            (False, None)      — still pending or no match yet
        """
        now = time.time()
        self._evict_expired(now)

        if body_embedding is None:
            return self._count_only(gender, age, age_group)

        # 1. Match against confirmed persons
        for person_id, person in self.persons.items():
            score = self._best_score(body_embedding, person["embeddings"])
            if score >= self.match_threshold:
                person["timestamp"] = now
                person["embeddings"] = self._update_embeddings(
                    person["embeddings"], body_embedding
                )
                # Enrich gender/age if not yet attributed
                if gender and gender != "Unknown":
                    self._try_attach_gender_to_record(person_id, person, gender, age, age_group)
                return (False, person_id)

        # 2. Match against pending
        for pending_key, pending in list(self.pending.items()):
            score = self._best_score(body_embedding, pending["embeddings"])
            if score >= self.pending_threshold:
                pending["count"] += 1
                pending["embeddings"] = self._update_embeddings(
                    pending["embeddings"], body_embedding
                )
                pending["timestamp"] = now
                if gender and gender != "Unknown":
                    pending.setdefault("gender_obs", []).append(gender)
                if age is not None:
                    pending.setdefault("age_obs", []).append(age)
                if pending["count"] >= self.confirmation_count:
                    person_id = self._promote(pending_key, pending)
                    return (True, person_id)
                return (False, None)

        # 3. New pending record
        self.pending[uuid.uuid4().hex] = {
            "embeddings": [body_embedding],
            "count": 1,
            "timestamp": now,
            "gender_obs": [gender] if gender and gender != "Unknown" else [],
            "age_obs": [age] if age is not None else [],
        }
        return (False, None)

    def attach_gender(
        self,
        person_id: int,
        gender: str,
        age: Optional[int],
        age_group: Optional[str],
    ) -> None:
        """Attach gender/age to an already-confirmed person."""
        person = self.persons.get(person_id)
        if person is None:
            return
        self._try_attach_gender_to_record(person_id, person, gender, age, age_group)

    def reset(self) -> None:
        """Clear all state and reset stats to zero."""
        self.persons = {}
        self.pending = {}
        self.next_person_id = 1
        self.stats = {
            "total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
            "age_groups": {
                "Children": 0, "Teens": 0, "Young Adults": 0,
                "Adults": 0, "Seniors": 0, "Unknown": 0,
            },
        }
        logger.info("BodyReIDTracker reset")

    def save_state(self) -> None:
        """Persist state to disk."""
        self.state_persistence.save_state(
            persons=self.persons,
            pending=self.pending,
            stats=self.stats,
            next_person_id=self.next_person_id,
        )
        self.last_save_time = time.time()

    def get_stats(self) -> dict:
        return self.stats.copy()

    def get_active_person_count(self) -> int:
        return len(self.persons)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _restore_state(self) -> None:
        try:
            persons, pending, stats, next_person_id = self.state_persistence.restore_state()
            self.persons = persons
            self.pending = pending
            self.stats = stats
            self.next_person_id = next_person_id
            logger.info(
                "BodyReIDTracker restored: %d confirmed, %d total",
                len(self.persons), self.stats["total_visitors"],
            )
        except Exception as e:
            logger.warning("BodyReIDTracker state restore failed, starting fresh: %s", e)

    def _promote(self, pending_key: str, pending: dict) -> int:
        """Promote a pending record to confirmed. Returns new person_id."""
        person_id = self.next_person_id
        self.next_person_id += 1

        gender_obs = pending.get("gender_obs", [])
        age_obs = pending.get("age_obs", [])
        gender = self._majority_gender(gender_obs)
        age = int(median(age_obs)) if age_obs else None
        age_group = get_age_group(age) if age is not None else "Unknown"

        self.persons[person_id] = {
            "embeddings": pending["embeddings"],
            "timestamp": pending["timestamp"],
            "gender": gender,
            "age_obs": age_obs,
            "age_group": age_group,
        }

        # LRU eviction
        if len(self.persons) > self.MAX_ACTIVE_PERSONS:
            oldest = min(self.persons, key=lambda pid: self.persons[pid]["timestamp"])
            del self.persons[oldest]

        del self.pending[pending_key]

        # Update stats
        self.stats["total_visitors"] += 1
        if gender == "Male":
            self.stats["male"] += 1
        elif gender == "Female":
            self.stats["female"] += 1
        else:
            self.stats["unknown"] += 1
        self.stats["age_groups"][age_group] = (
            self.stats["age_groups"].get(age_group, 0) + 1
        )

        if time.time() - self.last_save_time >= 30:
            self.save_state()

        return person_id

    def _count_only(
        self,
        gender: Optional[str],
        age: Optional[int],
        age_group: Optional[str],
    ) -> Tuple[bool, int]:
        """Bypass confirmation — immediate count (OSNet unavailable)."""
        person_id = self.next_person_id
        self.next_person_id += 1
        resolved_gender = gender if gender and gender != "Unknown" else None
        resolved_ag = age_group or "Unknown"
        self.persons[person_id] = {
            "embeddings": [],
            "timestamp": time.time(),
            "gender": resolved_gender,
            "age_obs": [age] if age is not None else [],
            "age_group": resolved_ag,
        }
        self.stats["total_visitors"] += 1
        if resolved_gender == "Male":
            self.stats["male"] += 1
        elif resolved_gender == "Female":
            self.stats["female"] += 1
        else:
            self.stats["unknown"] += 1
        self.stats["age_groups"][resolved_ag] = (
            self.stats["age_groups"].get(resolved_ag, 0) + 1
        )
        return (True, person_id)

    def _try_attach_gender_to_record(
        self,
        person_id: int,
        person: dict,
        gender: str,
        age: Optional[int],
        age_group: Optional[str],
    ) -> None:
        """Attach gender to a confirmed person if not already attributed."""
        if person.get("gender") in (None, "Unknown") and gender and gender != "Unknown":
            old_gender = person.get("gender")
            person["gender"] = gender
            person["age_group"] = age_group
            if age is not None:
                person.setdefault("age_obs", []).append(age)
            self._update_gender_stats(old_gender, gender)

    def _update_gender_stats(self, old_gender: Optional[str], new_gender: str) -> None:
        """Shift gender count: remove old, add new."""
        if old_gender in (None, "Unknown"):
            self.stats["unknown"] = max(0, self.stats["unknown"] - 1)
        elif old_gender == "Male":
            self.stats["male"] = max(0, self.stats["male"] - 1)
        elif old_gender == "Female":
            self.stats["female"] = max(0, self.stats["female"] - 1)

        if new_gender == "Male":
            self.stats["male"] += 1
        elif new_gender == "Female":
            self.stats["female"] += 1
        else:
            self.stats["unknown"] += 1

    def _evict_expired(self, now: float) -> None:
        expired_persons = [
            pid for pid, p in self.persons.items()
            if now - p["timestamp"] > self.memory_duration
        ]
        for pid in expired_persons:
            del self.persons[pid]

        expired_pending = [
            key for key, p in self.pending.items()
            if now - p["timestamp"] > self.pending_timeout
        ]
        for key in expired_pending:
            del self.pending[key]

    def _best_score(self, query: np.ndarray, stored: list) -> float:
        if not stored:
            return 0.0
        return max(self._cosine_similarity(query, emb) for emb in stored)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        if a is None or b is None:
            return 0.0
        a_n = a / (np.linalg.norm(a) + 1e-10)
        b_n = b / (np.linalg.norm(b) + 1e-10)
        return float(np.dot(a_n, b_n))

    def _update_embeddings(self, stored: list, new_emb: np.ndarray, max_stored: int = 5) -> list:
        stored = stored + [new_emb]
        return stored[-max_stored:]

    def _majority_gender(self, observations: list) -> Optional[str]:
        if not observations:
            return None
        counts = Counter(observations)
        top = counts.most_common(1)[0]
        return top[0]
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
pytest tests/test_body_reid_tracker.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/detection.py tests/test_body_reid_tracker.py
git commit -m "feat: add BodyReIDTracker to detection.py"
```

---

## Chunk 3: OSNetAnalyzer + VisitorStatePersistence

### Task 3: Add `OSNetAnalyzer` to `detection.py`

**Files:**
- Modify: `backend/detection.py` (add class before `BodyReIDTracker`)
- Modify: `requirements.txt`

- [ ] **Step 1: Add `torchreid` to `requirements.txt`**

Add this line to `requirements.txt` (after the reportlab line):

```
torchreid
```

- [ ] **Step 2: Install the dependency**

```bash
cd /home/adilhidayat/visitor-analytics
source venv/bin/activate
pip install torchreid 2>&1 | tail -5
```

Expected: `Successfully installed torchreid-...`

If torchreid fails to install from PyPI, use the git source:
```bash
pip install git+https://github.com/KaiyangZhou/deep-person-reid.git
```

- [ ] **Step 3: Add `OSNetAnalyzer` class to `backend/detection.py`**

Add this class after `EnsembleAnalyzer` and before `VisitorTracker`:

```python
class OSNetAnalyzer:
    """Extract body Re-ID embeddings using OSNet-x1.0 via torchreid.

    Input: full-body bbox crop from the resized 1280px frame.
    Output: 512-dim L2-normalised embedding, or None on failure/unavailability.
    """

    INPUT_H = 256
    INPUT_W = 128

    def __init__(self):
        self.available = False
        self.extractor = None
        self._init_model()

    def _init_model(self) -> None:
        try:
            import torchreid
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.extractor = torchreid.utils.FeatureExtractor(
                model_name="osnet_x1_0",
                device=device,
            )
            self.available = True
            logger.info("OSNetAnalyzer initialized (device=%s)", device)
        except Exception as e:
            logger.warning("OSNet unavailable — falling back to count-only mode: %s", e)
            self.available = False

    def extract(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
    ) -> Optional[np.ndarray]:
        """Extract body embedding from frame at bbox.

        Returns L2-normalised 512-dim float32 array or None.
        """
        if not self.available or self.extractor is None:
            return None

        x1, y1, x2, y2 = bbox
        h_frame, w_frame = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_frame, x2), min(h_frame, y2)

        if (x2 - x1) < 32 or (y2 - y1) < 32:
            return None

        try:
            crop = frame[y1:y2, x1:x2]
            resized = self._letterbox(crop)
            rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            features = self.extractor([rgb])  # shape (1, 512)
            emb = features[0].cpu().numpy().astype(np.float32)
            norm = np.linalg.norm(emb)
            if norm > 1e-10:
                emb = emb / norm
            return emb
        except Exception as e:
            logger.warning("OSNet inference error: %s", e)
            return None

    def _letterbox(self, img: np.ndarray) -> np.ndarray:
        """Letterbox to INPUT_H×INPUT_W preserving aspect ratio, black fill."""
        h, w = img.shape[:2]
        scale = min(self.INPUT_H / h, self.INPUT_W / w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.zeros((self.INPUT_H, self.INPUT_W, 3), dtype=np.uint8)
        pad_top = (self.INPUT_H - new_h) // 2
        pad_left = (self.INPUT_W - new_w) // 2
        canvas[pad_top:pad_top + new_h, pad_left:pad_left + new_w] = resized
        return canvas
```

- [ ] **Step 4: Smoke-test OSNetAnalyzer manually**

```bash
cd /home/adilhidayat/visitor-analytics/backend
source ../venv/bin/activate
python3 -c "
from detection import OSNetAnalyzer
import numpy as np
a = OSNetAnalyzer()
print('available:', a.available)
if a.available:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    emb = a.extract(frame, (50, 50, 200, 400))
    print('embedding shape:', emb.shape if emb is not None else None)
"
```

Expected: `available: True`, `embedding shape: (512,)`

- [ ] **Step 5: Commit**

```bash
git add backend/detection.py requirements.txt
git commit -m "feat: add OSNetAnalyzer for body Re-ID embedding extraction"
```

---

### Task 4: Update `VisitorStatePersistence` for `BodyReIDTracker`

**Files:**
- Modify: `backend/visitor_state.py`
- Modify: `tests/test_visitor_state.py`

- [ ] **Step 1: Read existing test file to understand what needs updating**

```bash
grep -n "save_state\|load_state\|restore_state\|next_pending\|pending_visitors" \
    tests/test_visitor_state.py | head -30
```

- [ ] **Step 2: Update `visitor_state.py` — replace `save_state` and add `restore_state`**

Replace the `save_state` method signature and add `restore_state`. The `load_state` method is kept for backward compat (existing `VisitorTracker` still calls it until we update `DetectionEngine`).

Find and replace the `save_state` method in `backend/visitor_state.py`:

```python
    def save_state(
        self,
        persons: Dict,
        pending: Dict,
        stats: Dict,
        next_person_id: int,
    ) -> None:
        """Save BodyReIDTracker state to disk."""
        try:
            state = {
                "persons": self._serialize_visitors(persons),
                "pending": self._serialize_visitors(pending),
                "stats": stats,
                "next_person_id": next_person_id,
            }
            atomic_write_json(self.state_file, state)
            logger.debug(
                "Saved body tracker state: %d confirmed, %d total",
                len(persons), stats["total_visitors"],
            )
        except Exception as e:
            logger.error("Error saving body tracker state: %s", e)

    def restore_state(self) -> tuple:
        """Load BodyReIDTracker state from disk.

        Returns:
            (persons, pending, stats, next_person_id)
        """
        default_stats = {
            "total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
            "age_groups": {
                "Children": 0, "Teens": 0, "Young Adults": 0,
                "Adults": 0, "Seniors": 0, "Unknown": 0,
            },
        }
        try:
            state = atomic_read_json(self.state_file, default={})
            if not state or "persons" not in state:
                return {}, {}, default_stats, 1

            persons = self._deserialize_visitors(state.get("persons", {}))
            pending = self._deserialize_visitors(state.get("pending", {}))
            stats = state.get("stats", default_stats)
            next_person_id = state.get("next_person_id", 1)

            # Ensure all age_group keys present
            for key in default_stats["age_groups"]:
                stats["age_groups"].setdefault(key, 0)

            logger.info(
                "Restored body tracker: %d confirmed, %d total",
                len(persons), stats["total_visitors"],
            )
            return persons, pending, stats, next_person_id
        except Exception as e:
            logger.error("Error restoring body tracker state: %s", e)
            return {}, {}, default_stats, 1
```

- [ ] **Step 3: Update `tests/test_visitor_state.py` to test new API**

The existing `TestPersistenceRoundTrip.test_save_and_load` calls `save_state(visitors, {}, stats, 2, 1)` with 5 positional args — this will raise `TypeError` once the signature changes to 4 params. **Replace the entire existing test class** with the new one below:

```python
class TestBodyReIDPersistence:
    def test_save_and_restore_roundtrip(self, tmp_path):
        from visitor_state import VisitorStatePersistence
        import numpy as np
        persistence = VisitorStatePersistence(data_dir=str(tmp_path))

        persons = {
            1: {"embeddings": [np.random.randn(512).astype(np.float32)],
                "timestamp": 1000.0, "gender": "Male",
                "age_obs": [30], "age_group": "Adults"}
        }
        pending = {}
        stats = {"total_visitors": 1, "male": 1, "female": 0, "unknown": 0,
                 "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0,
                                "Adults": 1, "Seniors": 0, "Unknown": 0}}

        persistence.save_state(persons, pending, stats, next_person_id=2)
        p2, pe2, s2, nid2 = persistence.restore_state()

        assert s2["total_visitors"] == 1
        assert nid2 == 2
        assert len(p2) == 1
        assert 1 in p2
        assert len(p2[1]["embeddings"]) == 1

    def test_restore_missing_file_returns_defaults(self, tmp_path):
        from visitor_state import VisitorStatePersistence
        persistence = VisitorStatePersistence(data_dir=str(tmp_path / "nonexistent"))
        persons, pending, stats, nid = persistence.restore_state()
        assert persons == {}
        assert stats["total_visitors"] == 0
        assert nid == 1
```

- [ ] **Step 3b: Archive old state file to avoid silent data loss**

The existing `backend/data/visitor_state.json` uses old keys (`"visitors"`, `"pending_visitors"`) that `restore_state()` won't recognise — it will start fresh. This is correct behaviour but must be explicit:

```bash
mv /home/adilhidayat/visitor-analytics/backend/data/visitor_state.json \
   /home/adilhidayat/visitor-analytics/backend/data/visitor_state.json.pre-body-reid-backup 2>/dev/null || true
```

- [ ] **Step 4: Run visitor state tests**

```bash
pytest tests/test_visitor_state.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/visitor_state.py tests/test_visitor_state.py
git commit -m "feat: update VisitorStatePersistence for BodyReIDTracker"
```

---

## Chunk 4: Backend Wiring

### Task 5: Update `DetectionEngine` — retire `VisitorTracker`, add `BodyReIDTracker` + `OSNetAnalyzer`

**Files:**
- Modify: `backend/detection.py` (DetectionEngine class, lines ~767-865)

- [ ] **Step 1: Update `DetectionEngine.__init__`**

Find the `DetectionEngine.__init__` method and replace it:

```python
    def __init__(self, gender_threshold: float = 0.6, similarity_threshold: float = 0.45):
        self.person_detector = PersonDetector()
        self.face_analyzer = EnsembleAnalyzer(confidence_threshold=gender_threshold)
        self.osnet = OSNetAnalyzer()
        self.body_tracker = BodyReIDTracker(
            match_threshold=similarity_threshold + 0.15,  # 0.60 default
            pending_threshold=similarity_threshold + 0.10,  # 0.55 default
            memory_duration=1800,
            confirmation_count=3,
            pending_timeout=30.0,
        )
        self.enable_gender = False
```

- [ ] **Step 2: Update `DetectionEngine` methods**

Replace `set_similarity_threshold`, `get_visitor_stats`, `reset_visitor_stats`, `get_active_visitors`:

```python
    def set_similarity_threshold(self, threshold: float):
        """Set body similarity threshold for re-identification."""
        self.body_tracker.match_threshold = max(0.0, min(1.0, threshold + 0.15))
        self.body_tracker.pending_threshold = max(0.0, min(1.0, threshold + 0.10))
        logger.info(f"Body similarity threshold set to {self.body_tracker.match_threshold}")

    def get_visitor_stats(self) -> Dict:
        """Get accumulated visitor statistics (unique persons)."""
        return self.body_tracker.get_stats()

    def reset_visitor_stats(self):
        """Reset visitor tracking stats."""
        self.body_tracker.reset()

    def get_active_visitors(self) -> int:
        """Get count of persons currently being tracked."""
        return self.body_tracker.get_active_person_count()
```

- [ ] **Step 3: Remove the dead `VisitorTracker` call from `process_frame` (cleanup only)**

Note: `process_frame` is **not called** by `streaming.py` — the stream loop calls `person_detector.detect()` and `face_analyzer.analyze()` directly. This is dead-code cleanup only with no functional effect.

In `DetectionEngine.process_frame`, find and remove the block that calls `self.visitor_tracker.check_visitor(...)` and the `stats["new_visitors"]` increment.

The `process_frame` method no longer needs to call `visitor_tracker`. Remove these lines from `process_frame`:

```python
                # Check if this is a new visitor using face re-identification
                if analysis["embedding"] is not None:
                    is_new, visitor_id = self.visitor_tracker.check_visitor(
                        analysis["embedding"],
                        analysis["gender"],
                        analysis["age_group"],
                        age=analysis["age"],
                    )
                    det.is_new_visitor = is_new
                    det.visitor_id = visitor_id
                    if is_new:
                        stats["new_visitors"] += 1
```

- [ ] **Step 4: Run all backend tests to ensure nothing is broken**

```bash
pytest tests/ -v --ignore=tests/test_websocket_load.py -x 2>&1 | tail -30
```

Expected: all tests PASS (some visitor_tracker tests may fail — that's OK, they'll be addressed next)

- [ ] **Step 5: Commit**

```bash
git add backend/detection.py
git commit -m "feat: wire BodyReIDTracker and OSNetAnalyzer into DetectionEngine, retire VisitorTracker"
```

---

### Task 6: Wire `streaming.py` — body Re-ID loop + PersonCaptureStore

**Files:**
- Modify: `backend/streaming.py`

- [ ] **Step 1: Add imports and PersonCaptureStore instantiation**

At the top of `streaming.py`, add import:

```python
try:
    from .person_capture_store import PersonCaptureStore
except ImportError:
    from person_capture_store import PersonCaptureStore
```

In `StreamManager.__init__`, `_project_root` is already defined on the line before `face_store`. Add `person_store` on the next line after `face_store`, reusing the existing variable:

```python
        self.person_store = PersonCaptureStore(
            capture_dir=os.path.join(_project_root, "backend", "data", "person_captures")
        )
```

- [ ] **Step 2: Update `_stream_loop` — add body Re-ID on every analysis frame**

**Important structural notes:**
- `analyses` is only defined inside the `if self.detection_engine.enable_gender and is_analysis_frame:` block. Body Re-ID must run even when `enable_gender=False`, so it lives inside `if is_analysis_frame:` (not inside the `enable_gender` guard).
- `OSNetAnalyzer.extract()` is a synchronous GPU call. Wrap it in `run_in_executor` like the face analysis gather to avoid blocking the event loop.

In `_stream_loop`, find the `if is_detection_frame:` block. Inside it, find the existing `if self.detection_engine.enable_gender and is_analysis_frame:` sub-block. **After** that entire sub-block (at the same indentation level as the `if enable_gender` block, i.e., still inside `if is_detection_frame:`), add:

```python
                    # --- Body Re-ID (independent of gender analysis) ---
                    if is_analysis_frame:
                        loop = asyncio.get_event_loop()
                        # Build per-detection gender/age from analyses if available
                        if self.detection_engine.enable_gender and 'analyses' in locals():
                            det_analyses = analyses
                        else:
                            det_analyses = [{}] * len(detections)

                        # Extract body embeddings in parallel (non-blocking)
                        body_embeddings = await asyncio.gather(*[
                            loop.run_in_executor(
                                None,
                                self.detection_engine.osnet.extract,
                                resized_frame,
                                det.bbox,
                            )
                            for det in detections
                        ], return_exceptions=True)

                        for det, body_emb, analysis in zip(detections, body_embeddings, det_analyses):
                            if isinstance(body_emb, Exception):
                                body_emb = None
                            gender = analysis.get("gender") if analysis else None
                            age = analysis.get("age") if analysis else None
                            age_group = analysis.get("age_group") if analysis else None

                            is_new, person_id = self.detection_engine.body_tracker.check_person(
                                body_emb,
                                gender=gender,
                                age=age,
                                age_group=age_group,
                            )

                            if person_id is not None:
                                det.visitor_id = person_id
                                det.is_new_visitor = is_new

                            if is_new and person_id is not None:
                                try:
                                    person_record = self.person_store.save_capture(
                                        resized_frame, det.bbox,
                                        person_id=person_id,
                                        gender=gender,
                                        age=age,
                                        age_group=age_group,
                                        is_new=True,
                                    )
                                    if person_record:
                                        await self._broadcast_person_capture(person_record)
                                except Exception as e:
                                    logger.error("Person capture error: %s", e)

                            elif not is_new and person_id is not None:
                                if gender and gender != "Unknown":
                                    self.detection_engine.body_tracker.attach_gender(
                                        person_id, gender, age, age_group
                                    )
                                try:
                                    person_record = self.person_store.save_capture(
                                        resized_frame, det.bbox,
                                        person_id=person_id,
                                        gender=gender,
                                        age=age,
                                        age_group=age_group,
                                        is_new=False,
                                    )
                                    if person_record:
                                        await self._broadcast_person_capture(person_record)
                                except Exception as e:
                                    logger.error("Person capture refresh error: %s", e)
```

- [ ] **Step 3: Add `_broadcast_person_capture` method**

After `_broadcast_face_capture`, add:

```python
    async def _broadcast_person_capture(self, record: dict) -> None:
        """Broadcast a person_capture event to all connected WebSocket clients."""
        message = json.dumps({
            "type": "person_capture",
            "data": {
                "id": record["id"],
                "url": f"/persons/{record['filename']}",
                "timestamp": record["timestamp"],
                "gender": record["gender"],
                "age": record["age"],
                "age_group": record["age_group"],
                "person_id": record["person_id"],
                "is_new": record["is_new"],
            }
        })
        await self.connection_manager.broadcast_frame(message)
```

- [ ] **Step 4: Update `save_interval` block to use body_tracker stats**

Find the block in `_stream_loop` that calls `self.data_storage.save_current_stats(...)` and verify it uses `visitor_stats` which already comes from `self.detection_engine.get_visitor_stats()` → `body_tracker.get_stats()`. No change needed here if the call already uses `visitor_stats`.

- [ ] **Step 5: Restart service and check logs**

```bash
echo "4\$\$p4r4d3" | sudo -S systemctl restart visitor-analytics.service
sleep 5
journalctl -u visitor-analytics.service --no-pager -n 30 | grep -i "osnet\|body\|person"
```

Expected: `OSNetAnalyzer initialized (device=cuda)` and `BodyReIDTracker initialized`

- [ ] **Step 6: Commit**

```bash
git add backend/streaming.py
git commit -m "feat: wire body Re-ID and PersonCaptureStore into streaming loop"
```

---

### Task 7: Update `main.py` — endpoints, shutdown, health, cleanup

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add `/persons` and `/persons/{filename}` endpoints**

After the `/faces/{filename}` endpoint (around line 645), add:

```python
@app.get("/persons", dependencies=[Depends(require_auth)])
async def list_persons():
    """Return the last 20 person captures, newest first."""
    records = stream_manager.person_store.get_recent(limit=20)
    return [{**r, "url": f"/persons/{r['filename']}"} for r in records]


@app.get("/persons/{filename}", dependencies=[Depends(require_auth)])
async def get_person_image(filename: str):
    """Serve a person body crop JPEG."""
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+\.jpg", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backend", "data", "person_captures", filename,
    )
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")
```

- [ ] **Step 2: Fix both shutdown handlers — replace `visitor_tracker` with `body_tracker`**

Find `_handle_shutdown_signal` (around line 241) and replace:
```python
        detection_engine.visitor_tracker.save_state()
```
with:
```python
        detection_engine.body_tracker.save_state()
```

Find the lifespan shutdown block (around line 289) and replace:
```python
        detection_engine.visitor_tracker.save_state()
```
with:
```python
        detection_engine.body_tracker.save_state()
```

- [ ] **Step 3: Add person cleanup task in `lifespan`**

In the lifespan function, after the `_face_cleanup_loop` task creation, add:

```python
    async def _person_cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                deleted = stream_manager.person_store.cleanup_expired()
                if deleted:
                    logger.info("Person capture cleanup: deleted %d expired files", deleted)
            except Exception as e:
                logger.error("Person capture cleanup error: %s", e)

    person_cleanup_task = asyncio.create_task(_person_cleanup_loop())
```

In the `yield` shutdown block, cancel and await both tasks:

```python
    cleanup_task.cancel()
    person_cleanup_task.cancel()
    try:
        await asyncio.gather(cleanup_task, person_cleanup_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass
```

Replace the existing `cleanup_task.cancel()` + await block with the above.

- [ ] **Step 4: Update `/health` endpoint — add `osnet_loaded`**

Find the health endpoint (around line 432) and update the `models` dict:

```python
        "models": {
            "yolo_loaded": detector.model_loaded,
            "insightface_loaded": detection_engine.face_analyzer.insightface.model_loaded,
            "osnet_loaded": detection_engine.osnet.available,
            "last_detection": detector.last_detection_time,
        },
```

- [ ] **Step 5: Run API tests**

```bash
pytest tests/test_api.py -v 2>&1 | tail -20
```

Expected: all tests PASS

- [ ] **Step 6: Verify endpoints work**

```bash
source venv/bin/activate
# Test health
curl -sk https://localhost/health | python3 -m json.tool | grep osnet

# Test persons endpoint
curl -sk https://localhost/persons | python3 -m json.tool
```

Expected: `"osnet_loaded": true` in health, `[]` or capture records in persons.

- [ ] **Step 7: Commit**

```bash
git add backend/main.py
git commit -m "feat: add /persons endpoints, update shutdown handlers and health for BodyReIDTracker"
```

---

## Chunk 5: Frontend

### Task 8: Add Person Captures panel — HTML, CSS, JS

**Files:**
- Modify: `frontend/index.html`
- Modify: `static/css/style.css`
- Modify: `static/js/app.js`

- [ ] **Step 1: Add Person Captures panel HTML**

In `frontend/index.html`, find the Face Captures panel (around line 260):

```html
                <!-- Face Captures -->
                <div class="stats-card face-captures-panel">
```

Insert the Person Captures panel **above** it:

```html
                <!-- Person Captures -->
                <div class="stats-card person-captures-panel">
                    <div class="person-captures-header">
                        <h3>Person Captures</h3>
                        <span class="person-capture-count" id="person-capture-count">0</span>
                    </div>
                    <div class="person-captures-body" id="person-captures-body">
                        <div class="person-captures-empty" id="person-captures-empty">No persons detected yet</div>
                    </div>
                </div>

```

- [ ] **Step 2: Add Person Captures CSS**

In `static/css/style.css`, after the `.face-captures-panel` block (around line 1239), add:

```css
/* =========================================================
   Person Captures Panel
   ========================================================= */
.person-captures-panel {
    padding: 0;
    overflow: hidden;
}

.person-captures-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}

.person-captures-header h3 {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary);
}

.person-capture-count {
    background: rgba(16, 185, 129, 0.15);
    color: #10b981;
    border: 1px solid rgba(16, 185, 129, 0.3);
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 0.1rem 0.55rem;
    min-width: 1.5rem;
    text-align: center;
}

.person-captures-body {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    padding: 0.6rem;
    overflow-y: auto;
    max-height: 220px;
}

.person-captures-empty {
    width: 100%;
    text-align: center;
    color: var(--text-secondary);
    font-size: 0.8rem;
    padding: 1rem 0;
}

.person-tile {
    position: relative;
    width: 56px;
    border-radius: 6px;
    overflow: hidden;
    border-left: 3px solid var(--unknown-color);
    background: rgba(255,255,255,0.05);
    animation: person-tile-in 0.2s ease-out;
    flex-shrink: 0;
}

@keyframes person-tile-in {
    from { opacity: 0; transform: scale(0.85); }
    to   { opacity: 1; transform: scale(1); }
}

.person-tile.male,   .person-tile-male   { border-left-color: #3b82f6; }
.person-tile.female, .person-tile-female { border-left-color: #ec4899; }

.person-tile-img {
    width: 100%;
    aspect-ratio: 1 / 2.2;
    object-fit: cover;
    display: block;
}

.person-tile-info {
    padding: 0.2rem 0.3rem;
    background: rgba(0,0,0,0.45);
}

.person-tile-gender {
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    color: #e2e8f0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.person-tile-age {
    font-size: 0.55rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
```

- [ ] **Step 3: Add Person Captures JS to `app.js`**

In the `constructor`, find where face capture DOM elements are cached (look for `face-captures-body`). Add the person capture elements right before or after:

```javascript
        // Person capture elements
        this.personCapturesBody = document.getElementById('person-captures-body');
        this.personCapturesEmpty = document.getElementById('person-captures-empty');
        this.personCaptureCount = document.getElementById('person-capture-count');
```

In the `init()` method, after `this.loadFaceCaptures()`, add:

```javascript
        this.loadPersonCaptures();
```

In the WebSocket `onmessage` handler, after the `face_capture` handler, add:

```javascript
                } else if (message.type === 'person_capture') {
                    this.prependPersonTile(message.data);
```

Add these two new methods to the class (after `loadFaceCaptures`):

```javascript
    buildPersonTile(capture) {
        const tile = document.createElement('div');
        const genderClass = (capture.gender || '').toLowerCase();
        tile.className = `person-tile ${genderClass}`;

        const img = document.createElement('img');
        img.className = 'person-tile-img';
        img.src = capture.url;
        img.alt = capture.gender || 'Person';
        img.loading = 'lazy';

        const info = document.createElement('div');
        info.className = 'person-tile-info';

        const genderEl = document.createElement('div');
        genderEl.className = 'person-tile-gender';
        this._setText(genderEl, capture.gender || '?');

        const ageEl = document.createElement('div');
        ageEl.className = 'person-tile-age';
        this._setText(ageEl, capture.age ? `${capture.age}y` : '');

        info.appendChild(genderEl);
        info.appendChild(ageEl);
        tile.appendChild(img);
        tile.appendChild(info);
        return tile;
    }

    prependPersonTile(capture, silent = false) {
        const body = document.getElementById('person-captures-body');
        const empty = document.getElementById('person-captures-empty');
        if (empty) empty.remove();

        body.insertBefore(this.buildPersonTile(capture), body.firstChild);

        // Rolling window: keep max 20 tiles
        while (body.children.length > 20) {
            body.removeChild(body.lastChild);
        }

        if (!silent) {
            const counter = document.getElementById('person-capture-count');
            if (counter) counter.textContent = parseInt(counter.textContent || '0') + 1;
        }
    }

    async loadPersonCaptures() {
        try {
            const resp = await fetch('/persons', { headers: this._headers() });
            if (!resp.ok) return;
            const captures = await resp.json();
            // API returns newest-first; reverse so prepend builds correct order
            [...captures].reverse().forEach(c => this.prependPersonTile(c, true));
        } catch (e) {
            console.warn('Could not load person captures:', e);
        }
    }
```

- [ ] **Step 4: Restart service and verify in browser**

```bash
echo "4\$\$p4r4d3" | sudo -S systemctl restart visitor-analytics.service
sleep 8
journalctl -u visitor-analytics.service --no-pager -n 20 | grep -i "osnet\|body\|person\|error"
```

Open the dashboard and confirm:
- "Person Captures" panel appears above "Face Captures"
- Counter badge shows green `0`
- After a person walks past the camera: a body crop tile appears in the panel
- `total_visitors` in "Today's Visitors" reflects body-tracked count

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html static/css/style.css static/js/app.js
git commit -m "feat: add Person Captures panel — HTML, CSS, and JS tile logic"
```

---

## Final Verification

- [ ] **Verify complete flow end-to-end**

```bash
# Check health — osnet_loaded should be true
curl -sk https://localhost/health | python3 -m json.tool

# Check stats — total_visitors is body-tracked
curl -sk https://localhost/stats | python3 -m json.tool | grep total_visitors

# Check person captures API
curl -sk https://localhost/persons | python3 -m json.tool

# Check face captures still work
curl -sk https://localhost/faces | python3 -m json.tool
```

- [ ] **Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_websocket_load.py 2>&1 | tail -20
```

Expected: all tests PASS

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: body Re-ID unique visitor tracking — complete implementation"
```
