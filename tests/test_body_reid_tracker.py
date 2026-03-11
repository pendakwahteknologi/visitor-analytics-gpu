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

    def test_attach_gender_updates_age_groups_stats(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))  # confirmed with unknown gender/age → "Unknown" age_group
        assert tracker.stats["age_groups"]["Unknown"] == 1
        tracker.attach_gender(1, "Female", age=25, age_group="Young Adults")
        assert tracker.stats["age_groups"]["Young Adults"] == 1
        assert tracker.stats["age_groups"]["Unknown"] == 0


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
    def test_evicts_oldest_when_at_capacity(self):
        with patch("detection.VisitorStatePersistence") as MockPersist:
            mock = MockPersist.return_value
            mock.restore_state.return_value = (
                {}, {},
                {"total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
                 "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0,
                                "Adults": 0, "Seniors": 0, "Unknown": 0}},
                1,
            )
            mock.save_state.return_value = None
            tracker = BodyReIDTracker(
                match_threshold=0.60,
                pending_threshold=0.55,
                confirmation_count=3,
                pending_timeout=30.0,
                max_active_persons=3,
            )

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


# ---------------------------------------------------------------------------
# Memory eviction
# ---------------------------------------------------------------------------

class TestMemoryEviction:
    def test_confirmed_person_evicted_after_memory_duration(self, tracker):
        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb))
        assert len(tracker.persons) == 1

        # Back-date the person's timestamp beyond memory_duration
        tracker.persons[1]["timestamp"] -= tracker.memory_duration + 1

        # Trigger eviction by calling check_person
        tracker.check_person(_rand_emb())
        assert 1 not in tracker.persons
