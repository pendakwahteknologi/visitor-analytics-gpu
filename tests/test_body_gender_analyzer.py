"""Unit tests for BodyGenderAnalyzer."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import numpy as np
import pytest
from unittest.mock import patch, MagicMock


class TestBodyGenderAnalyzer:
    def test_returns_male_above_threshold(self):
        """predict() returns 'Male' when pipeline label is 'male' with score >= threshold."""
        from detection import BodyGenderAnalyzer

        analyzer = BodyGenderAnalyzer()
        analyzer._pipe = MagicMock(return_value=[{"label": "male", "score": 0.90}])
        crop = np.zeros((120, 60, 3), dtype=np.uint8)

        with patch("PIL.Image.fromarray", return_value=MagicMock()), \
             patch("cv2.cvtColor", return_value=crop):
            result = analyzer.predict(crop)

        assert result == "Male"

    def test_returns_female_above_threshold(self):
        """predict() returns 'Female' for female label above threshold."""
        from detection import BodyGenderAnalyzer

        analyzer = BodyGenderAnalyzer()
        analyzer._pipe = MagicMock(return_value=[{"label": "female", "score": 0.85}])
        crop = np.zeros((120, 60, 3), dtype=np.uint8)

        with patch("PIL.Image.fromarray", return_value=MagicMock()), \
             patch("cv2.cvtColor", return_value=crop):
            result = analyzer.predict(crop)

        assert result == "Female"

    def test_returns_none_below_threshold(self):
        """predict() returns None when confidence < BODY_GENDER_CONFIDENCE (0.70)."""
        from detection import BodyGenderAnalyzer

        analyzer = BodyGenderAnalyzer()
        analyzer._pipe = MagicMock(return_value=[{"label": "male", "score": 0.50}])
        crop = np.zeros((120, 60, 3), dtype=np.uint8)

        with patch("PIL.Image.fromarray", return_value=MagicMock()), \
             patch("cv2.cvtColor", return_value=crop):
            result = analyzer.predict(crop)

        assert result is None

    def test_returns_none_on_empty_pipeline_result(self):
        """predict() returns None when the pipeline returns an empty list."""
        from detection import BodyGenderAnalyzer

        analyzer = BodyGenderAnalyzer()
        analyzer._pipe = MagicMock(return_value=[])
        crop = np.zeros((120, 60, 3), dtype=np.uint8)

        with patch("PIL.Image.fromarray", return_value=MagicMock()), \
             patch("cv2.cvtColor", return_value=crop):
            result = analyzer.predict(crop)

        assert result is None

    def test_pipe_is_lazy_loaded(self):
        """_pipe must be None until predict() is first called."""
        from detection import BodyGenderAnalyzer
        analyzer = BodyGenderAnalyzer()
        assert analyzer._pipe is None

    def test_detection_engine_has_body_gender_attribute(self):
        """DetectionEngine must expose self.body_gender as a BodyGenderAnalyzer instance."""
        from detection import DetectionEngine, BodyGenderAnalyzer
        with patch("detection.PersonDetector"), \
             patch("detection.EnsembleAnalyzer"), \
             patch("detection.OSNetAnalyzer"), \
             patch("detection.BodyReIDTracker"), \
             patch("detection.BodyGenderAnalyzer") as MockBGA:
            engine = DetectionEngine()
            MockBGA.assert_called_once()
            assert hasattr(engine, "body_gender")
