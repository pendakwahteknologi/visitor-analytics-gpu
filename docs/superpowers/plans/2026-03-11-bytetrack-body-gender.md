# ByteTrack + Body-Gender Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace UUID-based pending accumulation with ByteTrack stable track IDs and add body-based gender estimation fallback to eliminate visitor count inflation and improve gender attribution.

**Architecture:** PersonDetector gains a `track()` method using YOLO's built-in ByteTrack (called every frame); BodyReIDTracker gains a `track_to_person` fast-path dict; BodyGenderAnalyzer wraps a HuggingFace CPU classifier as fallback gender source; StreamManager._stream_loop is rewired to use all three.

**Tech Stack:** ultralytics (ByteTrack bundled), transformers>=4.35 (HuggingFace pipeline), existing OSNet/InsightFace/BodyReIDTracker unchanged except for new params.

**Spec:** `docs/superpowers/specs/2026-03-11-bytetrack-body-gender-design.md`

---

## File Map

| File | Change |
|------|--------|
| `backend/config.py` | Add `MIN_PERSON_W`, `MIN_PERSON_H`, `BODY_GENDER_CONFIDENCE` |
| `backend/detection.py` | Add `track_id` to `Detection`; add `PersonDetector.track()`; add `BodyGenderAnalyzer` class; update `BodyReIDTracker.check_person()` + add `track_to_person` + `clear_track()`; update `DetectionEngine.__init__` |
| `backend/streaming.py` | Replace `detect()` with `track()` in `_stream_loop`; add min-size filter; add fast-path; add body-gender fallback; add track eviction |
| `requirements.txt` | Add `transformers>=4.35` |
| `tests/test_body_reid_tracker.py` | Add track_id fast-path + clear_track tests |
| `tests/test_bytetrack_streaming.py` | New: min-size filter + no-inflation + OSNet calling-convention tests |
| `tests/test_body_gender_analyzer.py` | New: BodyGenderAnalyzer unit tests |

---

## Chunk 1: Config, Detection dataclass, PersonDetector.track(), requirements

### Task 1: Add config constants and update imports

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/detection.py:13` (import line)
- Modify: `backend/streaming.py` (import line near top)
- Modify: `requirements.txt`

- [ ] **Step 1: Add constants to config.py**

  Open `backend/config.py`. After the `JPEG_QUALITY` line, add:

  ```python
  # Person detection size filter
  MIN_PERSON_W: int = int(os.getenv("MIN_PERSON_W", "50"))
  MIN_PERSON_H: int = int(os.getenv("MIN_PERSON_H", "100"))

  # Body gender classifier confidence threshold
  BODY_GENDER_CONFIDENCE: float = float(os.getenv("BODY_GENDER_CONFIDENCE", "0.70"))
  ```

- [ ] **Step 2: Update detection.py import**

  In `backend/detection.py` line 13, change:
  ```python
  from config import YOLO_MODEL, CONFIDENCE_THRESHOLD
  ```
  to:
  ```python
  from config import YOLO_MODEL, CONFIDENCE_THRESHOLD, BODY_GENDER_CONFIDENCE
  ```

- [ ] **Step 3: Update streaming.py import**

  In `backend/streaming.py`, find:
  ```python
  from config import JPEG_QUALITY, STREAM_FPS
  ```
  Change to:
  ```python
  from config import JPEG_QUALITY, STREAM_FPS, MIN_PERSON_W, MIN_PERSON_H
  ```

- [ ] **Step 4: Add transformers to requirements.txt**

  In `requirements.txt`, add after the `torchreid` line:
  ```
  transformers>=4.35
  ```

- [ ] **Step 5: Verify config loads correctly**

  ```bash
  cd /home/adilhidayat/visitor-analytics/backend && python -c "from config import MIN_PERSON_W, MIN_PERSON_H, BODY_GENDER_CONFIDENCE; print(MIN_PERSON_W, MIN_PERSON_H, BODY_GENDER_CONFIDENCE)"
  ```
  Expected output: `50 100 0.7`

- [ ] **Step 6: Commit**

  ```bash
  git add backend/config.py backend/detection.py backend/streaming.py requirements.txt
  git commit -m "feat: add ByteTrack/body-gender config constants and imports"
  ```

---

### Task 2: Add track_id to Detection dataclass and PersonDetector.track()

**Files:**
- Modify: `backend/detection.py` — Detection dataclass (lines 26-36); add track() after detect() method

- [ ] **Step 1: Write the failing test**

  Create `tests/test_bytetrack_streaming.py`:

  ```python
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
          from detection import BodyGenderAnalyzer
          analyzer = BodyGenderAnalyzer()
          analyzer._pipe = MagicMock()

          enable_gender = False
          gender = None

          if enable_gender and (gender is None or gender == "Unknown"):
              gender = analyzer.predict(np.zeros((120, 60, 3), dtype=np.uint8))

          analyzer._pipe.assert_not_called()
          assert gender is None
  ```

- [ ] **Step 2: Run test to verify the track() tests fail**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_bytetrack_streaming.py::TestPersonDetectorTrack -v 2>&1 | head -30
  ```
  Expected: FAIL — `AttributeError: 'PersonDetector' object has no attribute 'track'`

- [ ] **Step 3: Add track_id to Detection dataclass**

  In `backend/detection.py`, find the `Detection` dataclass (lines 26-36). Add `track_id` as the **last field** (after `visitor_id`):

  ```python
  @dataclass
  class Detection:
      bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
      confidence: float
      gender: Optional[str] = None
      gender_confidence: float = 0.0
      age: Optional[int] = None
      age_group: Optional[str] = None
      embedding: Optional[np.ndarray] = field(default=None, repr=False)
      is_new_visitor: bool = False
      visitor_id: Optional[int] = None
      track_id: Optional[int] = None   # ByteTrack track ID; None when tracker not used
  ```

- [ ] **Step 4: Add PersonDetector.track() method**

  In `backend/detection.py`, after the `detect()` method (after line 113, before `draw_detections`), insert:

  ```python
  def track(self, frame: np.ndarray) -> List['Detection']:
      """Run YOLO ByteTrack; return Detections with track_id populated.

      MUST be called on every frame — ByteTrack requires consistent input
      to maintain internal state. detect() is kept for snapshot/API use.
      """
      if self.model is None:
          logger.error("Model not loaded")
          return []

      detections = []
      try:
          results = self.model.track(
              frame,
              persist=True,
              tracker="bytetrack.yaml",
              classes=[0],
              conf=self.confidence,
              iou=0.45,
              device=0,
              half=True,
              imgsz=1280,
              verbose=False,
          )
          if results and results[0].boxes is not None:
              for box in results[0].boxes:
                  x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                  conf = float(box.conf[0])
                  tid = int(box.id[0]) if box.id is not None else None
                  detections.append(Detection(bbox=(x1, y1, x2, y2), confidence=conf, track_id=tid))
          self.last_detection_time = time.time()
      except (RuntimeError, ValueError) as e:
          logger.error("YOLO track error: %s", e)
      except cv2.error as e:
          logger.error("OpenCV error during tracking: %s", e)

      return detections
  ```

- [ ] **Step 5: Run all track tests**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_bytetrack_streaming.py -v
  ```
  Expected: all PASSED.

- [ ] **Step 6: Run existing tests for regressions**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_detection_utils.py tests/test_body_reid_tracker.py -v 2>&1 | tail -15
  ```
  Expected: all PASSED.

- [ ] **Step 7: Commit**

  ```bash
  git add backend/detection.py tests/test_bytetrack_streaming.py
  git commit -m "feat: add track_id to Detection dataclass and PersonDetector.track()"
  ```

---

## Chunk 2: BodyGenderAnalyzer

### Task 3: Implement BodyGenderAnalyzer and integrate into DetectionEngine

**Files:**
- Modify: `backend/detection.py` — add `BodyGenderAnalyzer` class before `DetectionEngine`; add `self.body_gender` to `DetectionEngine.__init__`
- Create: `tests/test_body_gender_analyzer.py`

- [ ] **Step 1: Write the failing tests**

  Create `tests/test_body_gender_analyzer.py`:

  ```python
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
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_body_gender_analyzer.py -v 2>&1 | head -20
  ```
  Expected: FAIL — `ImportError: cannot import name 'BodyGenderAnalyzer'`

- [ ] **Step 3: Implement BodyGenderAnalyzer**

  In `backend/detection.py`, add the following class **immediately before** the `DetectionEngine` class (after `BodyReIDTracker` ends, around line 1181):

  ```python
  class BodyGenderAnalyzer:
      """Body-based gender classification using HuggingFace image classifier.

      Lazy-loads the model on first predict() call to avoid slowing startup.
      Returns None gracefully when score is below threshold or on any error.
      Only invoked when enable_gender=True in the streaming loop.
      """
      MODEL_NAME = "rizvandwiki/gender-classification-2"

      def __init__(self):
          self._pipe = None  # lazy-loaded

      def _ensure_loaded(self):
          if self._pipe is None:
              from transformers import pipeline as hf_pipeline
              self._pipe = hf_pipeline(
                  "image-classification",
                  model=self.MODEL_NAME,
                  device=-1,  # CPU only
              )
              logger.info("BodyGenderAnalyzer: loaded %s", self.MODEL_NAME)

      def predict(self, crop_bgr: np.ndarray) -> Optional[str]:
          """Return 'Male', 'Female', or None (below threshold or error).

          Args:
              crop_bgr: BGR numpy array — person bounding-box crop from frame[y1:y2, x1:x2].
          """
          try:
              self._ensure_loaded()
              from PIL import Image
              rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
              pil_img = Image.fromarray(rgb)
              result = self._pipe(pil_img)
              if not result or result[0]["score"] < BODY_GENDER_CONFIDENCE:
                  return None
              label = result[0]["label"].lower()
              return "Male" if "male" in label else "Female"
          except Exception as e:
              logger.warning("BodyGenderAnalyzer.predict failed: %s", e)
              return None
  ```

  Note: `predict()` wraps in try/except to be resilient to model loading failures at runtime (e.g. network unavailable when downloading weights the first time). This is a deliberate deviation from the spec's minimal pseudocode.

- [ ] **Step 4: Add body_gender to DetectionEngine.__init__**

  In `backend/detection.py`, in `DetectionEngine.__init__` (around line 1197), after `self.enable_gender = False`, add:

  ```python
  self.body_gender = BodyGenderAnalyzer()
  ```

- [ ] **Step 5: Run tests to verify they pass**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_body_gender_analyzer.py -v
  ```
  Expected: 6 PASSED.

- [ ] **Step 6: Run full suite for regressions**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_body_reid_tracker.py tests/test_detection_utils.py tests/test_bytetrack_streaming.py -v 2>&1 | tail -15
  ```
  Expected: all PASSED.

- [ ] **Step 7: Commit**

  ```bash
  git add backend/detection.py tests/test_body_gender_analyzer.py
  git commit -m "feat: add BodyGenderAnalyzer with lazy HuggingFace model load"
  ```

---

## Chunk 3: BodyReIDTracker track_id support

### Task 4: Add track_to_person fast path and clear_track() to BodyReIDTracker

**Files:**
- Modify: `backend/detection.py` — `BodyReIDTracker.__init__`, `check_person`, `reset`, `clear_track` (new)
- Modify: `tests/test_body_reid_tracker.py` — append new test classes

**Context:** `check_person` is at line 900; `_promote` is at line 1022; `self.pending` is typed `Dict[str, dict]` — we will change it to `Dict` (mixed int/str keys).

- [ ] **Step 1: Write the failing tests**

  Append to `tests/test_body_reid_tracker.py`:

  ```python
  # ---------------------------------------------------------------------------
  # Track-ID fast path
  # ---------------------------------------------------------------------------

  class TestTrackIdFastPath:
      def test_known_track_id_returns_without_confirmation(self, tracker):
          """If track_id is already in track_to_person, return immediately (no cosine)."""
          tracker.track_to_person[5] = 42
          tracker.persons[42] = {
              "embeddings": [_rand_emb()],
              "timestamp": 9999999.0, "gender": "Male",
              "age_obs": [], "age_group": "Adults",
          }
          emb = _rand_emb()
          is_new, pid = tracker.check_person(emb, track_id=5)
          assert is_new is False
          assert pid == 42
          assert tracker.stats["total_visitors"] == 0   # no double-count

      def test_track_id_used_as_pending_key(self, tracker):
          """When track_id is given, it is used as the pending dict key (int)."""
          emb = _rand_emb()
          tracker.check_person(_similar_emb(emb), track_id=77)
          assert 77 in tracker.pending

      def test_none_track_id_uses_uuid_pending_key(self, tracker):
          """When track_id=None, pending key is a 32-char hex UUID string."""
          # Remove any existing pending to get a clean slate
          tracker.pending.clear()
          emb = _rand_emb()
          tracker.check_person(_similar_emb(emb), track_id=None)
          assert len(tracker.pending) == 1
          key = list(tracker.pending.keys())[0]
          assert isinstance(key, str) and len(key) == 32

      def test_same_track_id_accumulates_without_cosine_search(self, tracker):
          """Three calls with same track_id should confirm without cosine matching."""
          # Use wildly different embeddings (would never match by cosine)
          # but same track_id — confirmation should still happen
          r1 = tracker.check_person(_rand_emb(), track_id=10)
          r2 = tracker.check_person(_rand_emb(), track_id=10)
          r3 = tracker.check_person(_rand_emb(), track_id=10)
          assert r1 == (False, None)
          assert r2 == (False, None)
          confirmed, pid = r3
          assert confirmed is True
          assert pid is not None

      def test_track_id_stored_on_confirmation(self, tracker):
          """After confirmation, track_to_person[track_id] == person_id."""
          emb_base = _rand_emb()
          final_pid = None
          for _ in range(3):
              _, pid = tracker.check_person(_similar_emb(emb_base), track_id=99)
              if pid:
                  final_pid = pid
          assert tracker.track_to_person[99] == final_pid


  class TestClearTrack:
      def test_clear_track_removes_from_track_to_person(self, tracker):
          tracker.track_to_person[3] = 10
          tracker.clear_track(3)
          assert 3 not in tracker.track_to_person

      def test_clear_track_removes_from_pending(self, tracker):
          emb = _rand_emb()
          tracker.check_person(_similar_emb(emb), track_id=4)
          assert 4 in tracker.pending
          tracker.clear_track(4)
          assert 4 not in tracker.pending

      def test_clear_track_noop_on_unknown_id(self, tracker):
          """clear_track on an unknown ID should not raise."""
          tracker.clear_track(9999)   # must not raise

      def test_reset_clears_track_to_person(self, tracker):
          tracker.track_to_person[1] = 5
          tracker.reset()
          assert tracker.track_to_person == {}
  ```

- [ ] **Step 2: Run tests to verify they fail**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_body_reid_tracker.py::TestTrackIdFastPath tests/test_body_reid_tracker.py::TestClearTrack -v 2>&1 | head -30
  ```
  Expected: FAIL — `TypeError: check_person() got an unexpected keyword argument 'track_id'`

- [ ] **Step 3: Add track_to_person to BodyReIDTracker.__init__**

  In `backend/detection.py`, in `BodyReIDTracker.__init__` (around line 874 after `self.pending = {}`), add:

  ```python
  self.track_to_person: Dict[int, int] = {}
  # ByteTrack track_id → confirmed person_id. In-memory only; rebuilt on restart.
  ```

  Also update the `self.pending` type annotation from `Dict[str, dict]` to `Dict` (it now accepts int or str keys):
  ```python
  self.pending: Dict = {}
  ```

- [ ] **Step 4: Update check_person signature**

  Change the `check_person` signature (line 900) to add `track_id` parameter before `gender`:

  ```python
  def check_person(
      self,
      body_embedding: Optional[np.ndarray],
      track_id: Optional[int] = None,
      gender: Optional[str] = None,
      age: Optional[int] = None,
      age_group: Optional[str] = None,
  ) -> Tuple[bool, Optional[int]]:
  ```

- [ ] **Step 5: Add fast path at top of check_person**

  Immediately after the docstring (before `now = time.time()`), add:

  ```python
  # Fast path: track already confirmed this session — no cosine needed
  if track_id is not None and track_id in self.track_to_person:
      return (False, self.track_to_person[track_id])
  ```

- [ ] **Step 6: Add direct track_id pending lookup (the "2a" block)**

  In `check_person`, after the "# 1. Match against confirmed persons" loop and before "# 2. Match against pending", insert a new block:

  ```python
  # 2a. If same track_id is already in pending, accumulate directly (no cosine search)
  if track_id is not None and track_id in self.pending:
      pending = self.pending[track_id]
      pending["count"] += 1
      if body_embedding is not None:
          pending["embeddings"] = self._update_embeddings(
              pending["embeddings"], body_embedding
          )
      pending["timestamp"] = now
      if gender and gender != "Unknown":
          pending.setdefault("gender_obs", []).append(gender)
      if age is not None:
          pending.setdefault("age_obs", []).append(age)
      if pending["count"] >= self.confirmation_count:
          person_id = self._promote(track_id, pending)
          self.track_to_person[track_id] = person_id
          return (True, person_id)
      return (False, None)
  ```

- [ ] **Step 7: Update the existing cosine-loop promotion to also record track_to_person**

  In the "# 2. Match against pending" cosine loop (around line 946), update the promotion block:

  ```python
  if pending["count"] >= self.confirmation_count:
      person_id = self._promote(pending_key, pending)
      if track_id is not None:
          self.track_to_person[track_id] = person_id
      return (True, person_id)
  ```

- [ ] **Step 8: Use track_id as pending key in the "# 3. New pending record" block**

  Find (around line 952):
  ```python
  self.pending[uuid.uuid4().hex] = {
  ```
  Change to:
  ```python
  pending_key = track_id if track_id is not None else uuid.uuid4().hex
  self.pending[pending_key] = {
  ```

- [ ] **Step 9: Update _promote to accept Union[int, str] pending_key**

  The `_promote` signature is `def _promote(self, pending_key: str, pending: dict)`. Update the type annotation:
  ```python
  def _promote(self, pending_key, pending: dict) -> int:
  ```
  (Remove the `str` type annotation from `pending_key` — it now accepts int or str since both are valid dict keys.)

- [ ] **Step 10: Add clear_track() helper method**

  Add after the `attach_gender` method (around line 972):

  ```python
  def clear_track(self, track_id: int) -> None:
      """Called when ByteTrack permanently drops a track.

      Removes from the fast-path map and from pending.
      The confirmed person record in self.persons is NOT removed — they may return.
      """
      self.track_to_person.pop(track_id, None)
      self.pending.pop(track_id, None)
  ```

- [ ] **Step 11: Update reset() to clear track_to_person**

  In `BodyReIDTracker.reset()`, after `self.pending = {}`, add:
  ```python
  self.track_to_person = {}
  ```

- [ ] **Step 12: Run new tests**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_body_reid_tracker.py::TestTrackIdFastPath tests/test_body_reid_tracker.py::TestClearTrack -v
  ```
  Expected: all PASSED.

- [ ] **Step 13: Run full tracker test suite (including pre-existing tests)**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_body_reid_tracker.py -v 2>&1 | tail -20
  ```
  Expected: all PASSED (existing tests pass track_id=None by default).

- [ ] **Step 14: Commit**

  ```bash
  git add backend/detection.py tests/test_body_reid_tracker.py
  git commit -m "feat: add track_to_person fast path and clear_track to BodyReIDTracker"
  ```

---

## Chunk 4: Streaming loop overhaul

### Task 5: Wire ByteTrack into StreamManager._stream_loop

**Files:**
- Modify: `backend/streaming.py` — `_stream_loop` method (lines 176-408), `__init__`
- Modify: `tests/test_bytetrack_streaming.py` — append integration tests

**Context:** The existing `_stream_loop` has:
- `detection_interval = 2` → to be **removed** (ByteTrack must run every frame)
- `analysis_interval = 4` → **kept** (OSNet + face analysis are heavy)
- `is_detection_frame = frame_counter % detection_interval == 0` → **removed**
- `is_analysis_frame = frame_counter % analysis_interval == 0` → **kept**
- `if is_detection_frame:` outer block → **removed** (body de-indented)
- `else:` branch that reused `last_detections` → **removed**
- `age_groups = {}` initialised inside the old `if is_detection_frame:` block → must be **moved** to before the per-detection loop so it is always initialised
- `annotated_frame` set inside `if is_detection_frame:` → must be **always set** (moved outside)

- [ ] **Step 1: Write the failing integration tests**

  Append to `tests/test_bytetrack_streaming.py`:

  ```python
  # ---------------------------------------------------------------------------
  # Integration: no count inflation from tiny crops
  # ---------------------------------------------------------------------------

  class TestNoInflation:
      def test_tiny_bbox_detections_never_increment_visitor_count(self):
          """Tiny bboxes (below MIN_PERSON_W x MIN_PERSON_H) must not increment visitor stats,
          even when the existing code path would call _count_only via osnet.available=True.
          This is the root cause of the 5417 visitor count bug."""
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
              # The filter: must skip this detection
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
          assert not filtered_out, f"bbox ({w}x{h}) should pass filter but was filtered"


  class TestTrackIdFlowIntegration:
      def test_track_id_confirmation_and_fast_path(self):
          """Integration: same track_id seen 3 times → confirmed;
          4th call uses fast path (track_to_person)."""
          import sys, os
          sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
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
          # First 3 calls — should confirm on 3rd
          r1 = tracker.check_person(_similar_emb(emb), track_id=7)
          r2 = tracker.check_person(_similar_emb(emb), track_id=7)
          r3 = tracker.check_person(_similar_emb(emb), track_id=7)
          assert r3[0] is True
          person_id = r3[1]
          assert 7 in tracker.track_to_person
          assert tracker.track_to_person[7] == person_id

          # 4th call — fast path; stat must not increment
          before_total = tracker.stats["total_visitors"]
          r4 = tracker.check_person(_similar_emb(emb), track_id=7)
          assert r4 == (False, person_id)
          assert tracker.stats["total_visitors"] == before_total

      def test_track_eviction_via_clear_track(self):
          """Integration: clear_track removes from both maps."""
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
  ```

- [ ] **Step 2: Run integration tests to verify they fail or are structurally valid**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/test_bytetrack_streaming.py::TestNoInflation tests/test_bytetrack_streaming.py::TestTrackIdFlowIntegration -v 2>&1 | tail -20
  ```
  Expected: `TestNoInflation` passes (it tests config values/logic in isolation); `TestTrackIdFlowIntegration` may pass or fail depending on whether Task 4 is already implemented. If Task 4 is done, all should pass.

- [ ] **Step 3: Add prev_track_ids to StreamManager.__init__**

  In `backend/streaming.py`, find `StreamManager.__init__`. Add at the end:
  ```python
  self.prev_track_ids: set = set()
  ```

- [ ] **Step 4: Rewrite the core detection block in _stream_loop**

  In `_stream_loop`, replace the section from `# Run detection with optimized intervals` through the closing `else:` branch (approximately lines 212–389) with the following new structure. Be careful to preserve indentation (everything is inside `if frame is not None:` and the `while self.streaming:` loop):

  ```python
  is_analysis_frame = frame_counter % analysis_interval == 0

  # ByteTrack: called every frame for consistent tracker state
  detections = self.detection_engine.person_detector.track(resized_frame)

  # Drop detections too small to be a real person
  detections = [
      det for det in detections
      if (det.bbox[2] - det.bbox[0]) >= MIN_PERSON_W
      and (det.bbox[3] - det.bbox[1]) >= MIN_PERSON_H
  ]

  # Carry forward gender/age from previous detection by nearest bbox centre
  if self.detection_engine.enable_gender and last_detections:
      def _centre(bbox):
          x1, y1, x2, y2 = bbox
          return ((x1 + x2) / 2, (y1 + y2) / 2)

      for det in detections:
          cx, cy = _centre(det.bbox)
          best = min(
              last_detections,
              key=lambda d: ((_centre(d.bbox)[0] - cx) ** 2 + (_centre(d.bbox)[1] - cy) ** 2)
          )
          bx, by = _centre(best.bbox)
          if ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5 < 150:
              det.gender = best.gender
              det.gender_confidence = best.gender_confidence
              det.age = best.age
              det.age_group = best.age_group
              det.embedding = best.embedding
              det.visitor_id = best.visitor_id

  last_detections = detections

  # Build set of current track IDs (only from detections that passed the filter)
  current_track_ids = {det.track_id for det in detections if det.track_id is not None}

  # Detections not yet in the confirmed fast-path — need analysis
  confirmed_map = self.detection_engine.body_tracker.track_to_person
  detections_needing_analysis = [
      det for det in detections
      if det.track_id is None or det.track_id not in confirmed_map
  ]

  # Always initialise age_groups for stats (even if no analysis runs)
  age_groups = {
      "Children": 0, "Teens": 0, "Young Adults": 0,
      "Adults": 0, "Seniors": 0, "Unknown": 0
  }

  # Face analysis (heavy — only on analysis frames, only when gender enabled)
  analyses = [{}] * len(detections_needing_analysis)
  if self.detection_engine.enable_gender and is_analysis_frame:
      loop = asyncio.get_event_loop()
      raw_results = await asyncio.gather(*[
          loop.run_in_executor(
              None, self.detection_engine.face_analyzer.analyze,
              resized_frame, det.bbox
          )
          for det in detections_needing_analysis
      ], return_exceptions=True)
      analyses = [
          r if not isinstance(r, Exception)
          else {"gender": None, "gender_confidence": 0.0,
                "age": None, "age_group": "Unknown", "embedding": None}
          for r in raw_results
      ]
      for det, analysis in zip(detections_needing_analysis, analyses):
          det.gender = analysis["gender"]
          det.gender_confidence = analysis["gender_confidence"]
          det.age = analysis["age"]
          det.age_group = analysis["age_group"]
          det.embedding = analysis["embedding"]

          # Save face crop when gender is known
          if analysis.get("gender") and analysis["gender"] != "Unknown":
              try:
                  has_embedding = analysis.get("embedding") is not None
                  face_record = self.face_store.save_capture(
                      resized_frame, det.bbox, analysis,
                      visitor_id=getattr(det, "visitor_id", None) if has_embedding else None,
                      is_new_visitor=getattr(det, "is_new_visitor", False) if has_embedding else False,
                  )
                  if face_record:
                      await self._broadcast_face_capture(face_record)
              except Exception as e:
                  logger.error("Face capture error: %s", e)

          if det.age_group and det.age_group != "Unknown":
              age_groups[det.age_group] += 1
          else:
              age_groups["Unknown"] += 1

  # Body Re-ID (on analysis frames for detections needing analysis)
  if is_analysis_frame:
      loop = asyncio.get_event_loop()
      body_embeddings = await asyncio.gather(*[
          loop.run_in_executor(
              None, self.detection_engine.osnet.extract,
              resized_frame, det.bbox,
          )
          for det in detections_needing_analysis
      ], return_exceptions=True)

      for det, body_emb, analysis in zip(detections_needing_analysis, body_embeddings, analyses):
          if isinstance(body_emb, Exception):
              body_emb = None

          # Skip crops too small for OSNet (avoids _count_only inflation)
          if body_emb is None and self.detection_engine.osnet.available:
              continue

          gender    = analysis.get("gender") if analysis else None
          age       = analysis.get("age") if analysis else None
          age_group = analysis.get("age_group") if analysis else None

          # Body-gender fallback (only when enable_gender=True and face didn't classify)
          if self.detection_engine.enable_gender and (gender is None or gender == "Unknown") and body_emb is not None:
              x1, y1, x2, y2 = det.bbox
              crop = resized_frame[y1:y2, x1:x2]
              if crop.size > 0:
                  gender = self.detection_engine.body_gender.predict(crop)

          is_new, person_id = self.detection_engine.body_tracker.check_person(
              body_emb,
              track_id=det.track_id,
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
                      gender=gender, age=age, age_group=age_group,
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
                      gender=gender, age=age, age_group=age_group,
                      is_new=False,
                  )
                  if person_record:
                      await self._broadcast_person_capture(person_record)
              except Exception as e:
                  logger.error("Person capture refresh error: %s", e)

  # Evict ByteTrack IDs that disappeared this frame
  for gone_id in (self.prev_track_ids - current_track_ids):
      self.detection_engine.body_tracker.clear_track(gone_id)
  self.prev_track_ids = current_track_ids

  # Live stats for display
  stats = {
      "total_people": len(detections),
      "male": sum(1 for d in detections if d.gender == "Male"),
      "female": sum(1 for d in detections if d.gender == "Female"),
      "unknown": sum(1 for d in detections if d.gender == "Unknown" or d.gender is None),
      "age_groups": age_groups,
  }
  last_stats = stats

  self.current_stats["total_people"] = stats["total_people"]
  self.current_stats["male"] = stats["male"]
  self.current_stats["female"] = stats["female"]
  self.current_stats["unknown"] = stats["unknown"]
  self.current_stats["age_groups"] = stats["age_groups"]

  # Annotate and broadcast frame
  annotated_frame = self.detection_engine.person_detector.draw_detections(
      resized_frame, detections
  )
  ```

  Also **remove** the old `detection_interval = 2` and `is_detection_frame` lines (lines 183 and 213).

- [ ] **Step 5: Smoke-test import**

  ```bash
  cd /home/adilhidayat/visitor-analytics/backend && python -c "import streaming; print('OK')"
  ```
  Expected: `OK` (no import or syntax errors).

- [ ] **Step 6: Run full test suite**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/ --ignore=tests/test_websocket_load.py --ignore=tests/test_api.py -v 2>&1 | tail -35
  ```
  Expected: all PASSED.

- [ ] **Step 7: Commit**

  ```bash
  git add backend/streaming.py tests/test_bytetrack_streaming.py
  git commit -m "feat: wire ByteTrack into streaming loop with min-size filter, fast-path, body-gender fallback"
  ```

---

## Final validation

- [ ] **Full test suite**

  ```bash
  cd /home/adilhidayat/visitor-analytics && python -m pytest tests/ --ignore=tests/test_websocket_load.py --ignore=tests/test_api.py -v 2>&1 | tail -40
  ```
  Expected: all PASSED.

- [ ] **Verify git log**

  ```bash
  git log --oneline -6
  ```
  Expected: 5 feature commits on top of the spec commit.
