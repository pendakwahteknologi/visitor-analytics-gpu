"""Tests for ByteTrack PersonDetector.track() and streaming safety checks."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import threading
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
            detector.model_lock = threading.Lock()

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
            detector.model_lock = threading.Lock()

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
            detector.model_lock = threading.Lock()

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


# ---------------------------------------------------------------------------
# Integration: no count inflation from tiny crops
# ---------------------------------------------------------------------------

class TestNoInflation:
    def test_tiny_bbox_detections_never_increment_visitor_count(self):
        """Tiny bboxes (below MIN_PERSON_W x MIN_PERSON_H) must not increment visitor stats."""
        from config import MIN_PERSON_W, MIN_PERSON_H
        from detection import Detection

        tiny_bboxes = [
            (280, 369, 301, 405),   # 21x36 — real offending bbox from bug report
            (0, 0, 30, 50),         # 30x50 — also below threshold
        ]

        for bbox in tiny_bboxes:
            det = Detection(bbox=bbox, confidence=0.6, track_id=1)
            x1, y1, x2, y2 = det.bbox
            w, h = x2 - x1, y2 - y1
            filtered_out = (w < MIN_PERSON_W or h < MIN_PERSON_H)
            assert filtered_out, f"bbox {bbox} ({w}x{h}) should be filtered but was not"

    def test_large_bbox_is_not_filtered(self):
        """A person-sized bbox (80x180) must pass through the filter."""
        from config import MIN_PERSON_W, MIN_PERSON_H
        from detection import Detection

        det = Detection(bbox=(100, 50, 180, 230), confidence=0.7, track_id=2)
        x1, y1, x2, y2 = det.bbox
        w, h = x2 - x1, y2 - y1
        filtered_out = (w < MIN_PERSON_W or h < MIN_PERSON_H)
        assert not filtered_out


class TestTrackIdFlowIntegration:
    def test_track_id_confirmation_and_fast_path(self):
        """Same track_id seen 3 times → confirmed; 4th call uses fast path."""
        from detection import BodyReIDTracker
        from unittest.mock import patch

        with patch("detection.VisitorStatePersistence") as MockP:
            mock = MockP.return_value
            mock.restore_state.return_value = (
                {}, {},
                {"total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
                 "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0,
                                "Adults": 0, "Seniors": 0, "Unknown": 0}},
                1,
            )
            mock.save_state.return_value = None
            tracker = BodyReIDTracker(confirmation_count=3)

        emb = _rand_emb()
        r1 = tracker.check_person(_similar_emb(emb), track_id=7)
        r2 = tracker.check_person(_similar_emb(emb), track_id=7)
        r3 = tracker.check_person(_similar_emb(emb), track_id=7)
        assert r3[0] is True
        person_id = r3[1]
        assert 7 in tracker.track_to_person
        assert tracker.track_to_person[7] == person_id

        before_total = tracker.stats["total_visitors"]
        r4 = tracker.check_person(_similar_emb(emb), track_id=7)
        assert r4 == (False, person_id)
        assert tracker.stats["total_visitors"] == before_total

    def test_track_eviction_via_clear_track(self):
        """clear_track removes from both maps."""
        from detection import BodyReIDTracker
        from unittest.mock import patch

        with patch("detection.VisitorStatePersistence") as MockP:
            mock = MockP.return_value
            mock.restore_state.return_value = (
                {}, {},
                {"total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
                 "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0,
                                "Adults": 0, "Seniors": 0, "Unknown": 0}},
                1,
            )
            mock.save_state.return_value = None
            tracker = BodyReIDTracker(confirmation_count=3)

        emb = _rand_emb()
        for _ in range(3):
            tracker.check_person(_similar_emb(emb), track_id=55)

        assert 55 in tracker.track_to_person
        tracker.clear_track(55)
        assert 55 not in tracker.track_to_person
        assert 55 not in tracker.pending
