"""Unit tests for detection utility functions."""

import numpy as np
import pytest

from detection import get_age_group, Detection, MIN_FACE_SIZE


# ---------------------------------------------------------------------------
# get_age_group
# ---------------------------------------------------------------------------

class TestGetAgeGroup:
    def test_children(self):
        assert get_age_group(0) == "Children"
        assert get_age_group(5) == "Children"
        assert get_age_group(12) == "Children"

    def test_teens(self):
        assert get_age_group(13) == "Teens"
        assert get_age_group(17) == "Teens"

    def test_young_adults(self):
        assert get_age_group(18) == "Young Adults"
        assert get_age_group(30) == "Young Adults"

    def test_adults(self):
        assert get_age_group(31) == "Adults"
        assert get_age_group(50) == "Adults"

    def test_seniors(self):
        assert get_age_group(51) == "Seniors"
        assert get_age_group(90) == "Seniors"

    def test_boundary_values(self):
        assert get_age_group(12) == "Children"
        assert get_age_group(13) == "Teens"
        assert get_age_group(17) == "Teens"
        assert get_age_group(18) == "Young Adults"
        assert get_age_group(30) == "Young Adults"
        assert get_age_group(31) == "Adults"
        assert get_age_group(50) == "Adults"
        assert get_age_group(51) == "Seniors"


# ---------------------------------------------------------------------------
# Detection dataclass
# ---------------------------------------------------------------------------

class TestDetection:
    def test_defaults(self):
        det = Detection(bbox=(0, 0, 100, 200), confidence=0.8)
        assert det.gender is None
        assert det.gender_confidence == 0.0
        assert det.age is None
        assert det.embedding is None
        assert det.is_new_visitor is False
        assert det.visitor_id is None

    def test_with_all_fields(self):
        emb = np.random.randn(512).astype(np.float32)
        det = Detection(
            bbox=(10, 20, 110, 220),
            confidence=0.95,
            gender="Male",
            gender_confidence=0.9,
            age=25,
            age_group="Young Adults",
            embedding=emb,
            is_new_visitor=True,
            visitor_id=42,
        )
        assert det.gender == "Male"
        assert det.age == 25
        assert det.visitor_id == 42
        assert det.embedding is emb


# ---------------------------------------------------------------------------
# MIN_FACE_SIZE constant
# ---------------------------------------------------------------------------

class TestMinFaceSize:
    def test_value(self):
        assert MIN_FACE_SIZE == 40
