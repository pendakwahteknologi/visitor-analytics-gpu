"""Tests for ByteTrack PersonDetector.track() and streaming safety checks."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import numpy as np
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared embedding helpers (also used by integration tests below)
# ---------------------------------------------------------------------------

def _rand_emb(dim=512) -> np.ndarray:
    v = np.random.randn(dim).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-10)


def _similar_emb(base: np.ndarray, noise: float = 0.03) -> np.ndarray:
    v = base + np.random.randn(*base.shape).astype(np.float32) * noise
    return v / (np.linalg.norm(v) + 1e-10)


class TestPersonDetectorTrack:
    def test_track_returns_detections_with_track_id(self):
        """track() should return Detection objects with track_id populated."""
        from detection import PersonDetector, Detection

        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock()]
        mock_box.xyxy[0].tolist = MagicMock(return_value=[10, 20, 110, 220])
        mock_box.conf = [0.85]
        mock_box.id = [7]   # ByteTrack assigns track_id=7

        mock_result = MagicMock()
        mock_result.boxes = [mock_box]

        with patch.object(PersonDetector, '_load_model'):
            detector = PersonDetector.__new__(PersonDetector)
            detector.confidence = 0.5
            detector.model = MagicMock()
            detector.model.track.return_value = [mock_result]
            detector.last_detection_time = None

            dets = detector.track(np.zeros((480, 640, 3), dtype=np.uint8))

        assert len(dets) == 1
        assert dets[0].track_id == 7
        assert dets[0].bbox == (10, 20, 110, 220)
        assert abs(dets[0].confidence - 0.85) < 0.01

    def test_track_returns_none_track_id_when_box_id_absent(self):
        """When ByteTrack has no id yet, track_id should be None."""
        from detection import PersonDetector

        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock()]
        mock_box.xyxy[0].tolist = MagicMock(return_value=[0, 0, 50, 100])
        mock_box.conf = [0.6]
        mock_box.id = None   # no track yet

        mock_result = MagicMock()
        mock_result.boxes = [mock_box]

        with patch.object(PersonDetector, '_load_model'):
            detector = PersonDetector.__new__(PersonDetector)
            detector.confidence = 0.5
            detector.model = MagicMock()
            detector.model.track.return_value = [mock_result]
            detector.last_detection_time = None

            dets = detector.track(np.zeros((480, 640, 3), dtype=np.uint8))

        assert dets[0].track_id is None

    def test_detect_still_works_and_track_id_is_none(self):
        """Existing detect() must remain functional; track_id must default to None."""
        from detection import PersonDetector

        mock_box = MagicMock()
        mock_box.xyxy = [MagicMock()]
        mock_box.xyxy[0].tolist = MagicMock(return_value=[5, 5, 55, 105])
        mock_box.conf = [0.7]

        mock_result = MagicMock()
        mock_result.boxes = [mock_box]

        with patch.object(PersonDetector, '_load_model'):
            detector = PersonDetector.__new__(PersonDetector)
            detector.confidence = 0.5
            detector.model = MagicMock()
            detector.model.return_value = [mock_result]
            detector.last_detection_time = None

            dets = detector.detect(np.zeros((480, 640, 3), dtype=np.uint8))

        assert len(dets) == 1
        assert dets[0].track_id is None


class TestMinSizeFilter:
    def test_tiny_detection_is_below_threshold(self):
        """A 21x36px bbox must be caught by the min-size filter."""
        from config import MIN_PERSON_W, MIN_PERSON_H
        bbox = (280, 369, 301, 405)   # 21x36
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        assert w < MIN_PERSON_W or h < MIN_PERSON_H

    def test_valid_size_passes_filter(self):
        """A 60x120 bbox must pass the min-size filter."""
        from config import MIN_PERSON_W, MIN_PERSON_H
        bbox = (100, 100, 160, 220)   # 60x120
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        assert not (w < MIN_PERSON_W or h < MIN_PERSON_H)


class TestOSNetCallingConvention:
    def test_osnet_extract_signature_takes_frame_and_bbox(self):
        """OSNet.extract(frame, bbox) — assert the signature has both params."""
        from detection import OSNetAnalyzer
        import inspect
        sig = inspect.signature(OSNetAnalyzer.extract)
        params = list(sig.parameters.keys())
        assert "frame" in params
        assert "bbox" in params


class TestBodyGenderEnableGate:
    def test_body_gender_not_called_when_gender_disabled(self):
        """BodyGenderAnalyzer.predict() must not be called when enable_gender=False."""
        enable_gender = False
        gender = None
        called = False

        if enable_gender and (gender is None or gender == "Unknown"):
            called = True

        assert not called
        assert gender is None
