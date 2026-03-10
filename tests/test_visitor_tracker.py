"""Unit tests for VisitorTracker logic.

These tests use a lightweight VisitorTracker with mocked persistence
so they run without ML models or disk I/O.
"""

import time
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from detection import VisitorTracker, get_age_group


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _random_embedding(dim=512) -> np.ndarray:
    """Return a random unit-norm embedding."""
    v = np.random.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-10)


def _similar_embedding(base: np.ndarray, noise: float = 0.05) -> np.ndarray:
    """Return an embedding close to *base*."""
    v = base + np.random.randn(*base.shape).astype(np.float32) * noise
    return v / (np.linalg.norm(v) + 1e-10)


@pytest.fixture
def tracker():
    """Create a VisitorTracker with mocked persistence."""
    with patch("detection.VisitorStatePersistence") as MockPersist:
        mock_instance = MockPersist.return_value
        mock_instance.load_state.return_value = {
            "visitors": {},
            "pending_visitors": {},
            "stats": {
                "total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
                "age_groups": {
                    "Children": 0, "Teens": 0, "Young Adults": 0,
                    "Adults": 0, "Seniors": 0, "Unknown": 0,
                },
            },
            "next_visitor_id": 1,
            "next_pending_id": 1,
        }
        mock_instance.save_state.return_value = None

        t = VisitorTracker(
            similarity_threshold=0.45,
            memory_duration=1800,
            confirmation_count=3,
            pending_timeout=30.0,
        )
        yield t


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCosienSimilarity:
    def test_identical(self, tracker):
        v = _random_embedding()
        assert tracker._cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-5)

    def test_orthogonal(self, tracker):
        a = np.zeros(512, dtype=np.float32)
        a[0] = 1.0
        b = np.zeros(512, dtype=np.float32)
        b[1] = 1.0
        assert tracker._cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-5)

    def test_none_returns_zero(self, tracker):
        assert tracker._cosine_similarity(None, _random_embedding()) == 0.0
        assert tracker._cosine_similarity(_random_embedding(), None) == 0.0


class TestAgeBonus:
    def test_exact_match(self, tracker):
        assert tracker._calculate_age_bonus("Adults", "Adults") == 0.10

    def test_adjacent(self, tracker):
        assert tracker._calculate_age_bonus("Teens", "Young Adults") == 0.05

    def test_one_apart(self, tracker):
        assert tracker._calculate_age_bonus("Children", "Young Adults") == 0.02

    def test_far_apart(self, tracker):
        assert tracker._calculate_age_bonus("Children", "Seniors") == 0.0

    def test_unknown(self, tracker):
        assert tracker._calculate_age_bonus("Unknown", "Adults") == 0.05


class TestConfirmationSystem:
    """The tracker requires 3 detections before a visitor is confirmed."""

    def test_single_detection_not_counted(self, tracker):
        emb = _random_embedding()
        is_new, vid = tracker.check_visitor(emb, "Male", "Adults", age=35)
        assert is_new is False
        assert vid == -1
        assert tracker.stats["total_visitors"] == 0

    def test_two_detections_still_pending(self, tracker):
        emb = _random_embedding()
        tracker.check_visitor(emb, "Male", "Adults", age=35)
        is_new, vid = tracker.check_visitor(
            _similar_embedding(emb), "Male", "Adults", age=36
        )
        assert is_new is False
        assert tracker.stats["total_visitors"] == 0

    def test_three_detections_confirms(self, tracker):
        emb = _random_embedding()
        tracker.check_visitor(emb, "Male", "Adults", age=35)
        tracker.check_visitor(_similar_embedding(emb), "Male", "Adults", age=36)
        is_new, vid = tracker.check_visitor(
            _similar_embedding(emb), "Male", "Adults", age=34
        )
        assert is_new is True
        assert vid >= 1
        assert tracker.stats["total_visitors"] == 1
        assert tracker.stats["male"] == 1

    def test_different_people_separate_visitors(self, tracker):
        # Person A
        emb_a = _random_embedding()
        for _ in range(3):
            tracker.check_visitor(_similar_embedding(emb_a), "Female", "Teens", age=15)
        # Person B (different embedding)
        emb_b = _random_embedding()
        for _ in range(3):
            tracker.check_visitor(_similar_embedding(emb_b), "Male", "Adults", age=40)

        assert tracker.stats["total_visitors"] == 2
        assert tracker.stats["female"] == 1
        assert tracker.stats["male"] == 1


class TestReidentification:
    """Once confirmed, a visitor should be recognised and not double-counted."""

    def test_reidentified_after_confirmation(self, tracker):
        emb = _random_embedding()
        # Confirm
        for _ in range(3):
            tracker.check_visitor(_similar_embedding(emb), "Male", "Adults", age=35)
        assert tracker.stats["total_visitors"] == 1

        # Re-detect same person many more times
        for _ in range(5):
            is_new, _ = tracker.check_visitor(
                _similar_embedding(emb), "Male", "Adults", age=35
            )
            assert is_new is False

        assert tracker.stats["total_visitors"] == 1  # Still 1


class TestMedianAge:
    """Visitor age should stabilise via median over multiple observations."""

    def test_median_age_group_stabilises(self, tracker):
        emb = _random_embedding()
        # Observations with ages: 29, 31, 30 → median=30 → Young Adults
        ages = [29, 31, 30]
        for a in ages:
            tracker.check_visitor(_similar_embedding(emb), "Male", get_age_group(a), age=a)

        assert tracker.stats["total_visitors"] == 1
        # Confirmed visitor should have median age 30 → Young Adults
        vid = list(tracker.visitors.keys())[0]
        assert tracker.visitors[vid]["age_group"] == "Young Adults"


class TestEviction:
    def test_evicts_when_over_capacity(self, tracker):
        tracker.MAX_ACTIVE_VISITORS = 5
        # Create 7 confirmed visitors (eviction happens at start of check_visitor,
        # so the 6th add brings count to 6, then next check_visitor evicts to 5,
        # then the 7th add brings it to 6, etc.)
        for i in range(7):
            emb = _random_embedding()
            for _ in range(3):
                tracker.check_visitor(_similar_embedding(emb), "Male", "Adults", age=30)

        # After the 7th visitor's check_visitor calls, eviction should have run
        # Trigger one more check to force eviction of excess
        tracker._evict_oldest_visitors()
        assert len(tracker.visitors) <= 5


class TestResetStats:
    def test_reset_clears_everything(self, tracker):
        emb = _random_embedding()
        for _ in range(3):
            tracker.check_visitor(_similar_embedding(emb), "Female", "Teens", age=15)

        assert tracker.stats["total_visitors"] == 1
        tracker.reset_stats()
        assert tracker.stats["total_visitors"] == 0
        assert tracker.stats["female"] == 0
        assert len(tracker.visitors) == 0
        assert len(tracker.pending_visitors) == 0


class TestNoneEmbedding:
    def test_none_returns_not_new(self, tracker):
        is_new, vid = tracker.check_visitor(None, "Male", "Adults")
        assert is_new is False
        assert vid == -1
