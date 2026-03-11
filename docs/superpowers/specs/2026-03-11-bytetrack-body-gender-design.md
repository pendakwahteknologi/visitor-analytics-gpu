# ByteTrack + Body-Gender Estimation Design Spec

**Date:** 2026-03-11
**Feature:** Surveillance-ready single-camera visitor tracking

---

## Goal

Replace the UUID-per-crop pending accumulation pattern with ByteTrack-based within-scene tracking to eliminate count inflation from tiny false-positive crops, and add body-based gender estimation as a fallback when InsightFace cannot detect a face.

---

## Background & Motivation

### Root cause of inflated visitor counts

YOLO occasionally detects very small (21×36 px) false-positive "persons" in busy backgrounds. These crops are too small for OSNet (requires ≥32 px in each dimension), so `extract()` returns `None`. The current code calls `_count_only()` when embedding is None, treating every tiny detection as a new unique visitor. At 4.5 analysis frames/second this caused the count to reach 5417 in a short session.

### ByteTrack solves two problems at once

1. **Min-size filter** — tracked objects that never grow above the size threshold are filtered early.
2. **Stable track IDs** — ByteTrack assigns a consistent `track_id` to each person while they remain in frame. The same `track_id` carries the pending confirmation across frames without relying on cosine similarity.

---

## Architecture

```
PersonDetector.track(frame) [every frame]      ← YOLO ByteTrack, returns Detections with track_id
    │
    ▼
StreamManager._stream_loop()
    ├─ min-size filter (drop W<50 or H<100)
    ├─ track_id fast path (skip heavy analysis if track already confirmed)
    ├─ OSNet + FaceAnalyzer run every analysis_interval frames
    └─ body gender fallback (InsightFace failed → BodyGenderAnalyzer)
    │
    ▼
BodyReIDTracker.check_person(emb, track_id, gender, age, age_group)
    ├─ fast path: track_id in track_to_person → return person_id (no cosine)
    ├─ confirmation: pending[track_id].count accumulates
    └─ re-ID: cosine similarity vs confirmed persons (returning visitor)
```

---

## Components

### 1. `backend/config.py` — New constants

```python
MIN_PERSON_W: int = 50        # minimum bounding-box width (pixels) to process
MIN_PERSON_H: int = 100       # minimum bounding-box height (pixels) to process
BODY_GENDER_CONFIDENCE: float = 0.70  # minimum confidence for body-gender classification
```

### 1a. Import updates required in other modules

**`backend/detection.py`** — add `BODY_GENDER_CONFIDENCE` to the config import:

```python
# Before:
from config import YOLO_MODEL, CONFIDENCE_THRESHOLD
# After:
from config import YOLO_MODEL, CONFIDENCE_THRESHOLD, BODY_GENDER_CONFIDENCE
```

**`backend/streaming.py`** — add `MIN_PERSON_W`, `MIN_PERSON_H` to the config import:

```python
# Before:
from config import JPEG_QUALITY, STREAM_FPS
# After:
from config import JPEG_QUALITY, STREAM_FPS, MIN_PERSON_W, MIN_PERSON_H
```

### 2. `backend/detection.py` — `Detection` dataclass

`track_id` is added as the **last field** in the dataclass (after all existing fields), so existing positional constructions are unaffected:

```python
@dataclass
class Detection:
    # ... all existing fields unchanged ...
    track_id: Optional[int] = None   # ByteTrack ID; None when tracker not used
```

### 3. `backend/detection.py` — `PersonDetector.track()`

New method alongside existing `detect()`. Uses the same GPU/precision flags as `detect()`:

```python
def track(self, frame: np.ndarray) -> List[Detection]:
    """Run YOLO ByteTrack on frame; return Detections with track_id populated.

    Must be called on EVERY frame for ByteTrack's internal state to be consistent.
    """
    results = self.model.track(
        frame,
        persist=True,
        tracker="bytetrack.yaml",
        classes=[0],               # person only
        conf=self.confidence,      # attribute is self.confidence (not conf_thresh)
        iou=0.45,
        device=0,                  # GPU (same as detect())
        half=True,                 # FP16 (same as detect())
        imgsz=1280,                # (same as detect())
        verbose=False,
    )
    detections = []
    if results and results[0].boxes is not None:
        boxes = results[0].boxes
        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            tid = int(box.id[0]) if box.id is not None else None
            detections.append(Detection(bbox=(x1, y1, x2, y2), confidence=conf, track_id=tid))
    return detections
```

`detect()` remains **unchanged** — used by the `/capture` snapshot API.

### 4. `backend/detection.py` — `BodyGenderAnalyzer`

New class. Wraps HuggingFace `rizvandwiki/gender-classification-2` (MobileNet-V2 fine-tuned on gender). Lazy-loaded on first call to avoid slowing startup. Only runs when `enable_gender=True` (see section 6).

```python
class BodyGenderAnalyzer:
    MODEL_NAME = "rizvandwiki/gender-classification-2"

    def __init__(self):
        self._pipe = None   # lazy-loaded on first predict() call

    def _ensure_loaded(self):
        if self._pipe is None:
            from transformers import pipeline as hf_pipeline
            self._pipe = hf_pipeline(
                "image-classification",
                model=self.MODEL_NAME,
                device=-1,   # CPU only
            )

    def predict(self, crop_bgr: np.ndarray) -> Optional[str]:
        """
        Returns "Male", "Female", or None (below confidence threshold).
        crop_bgr is a BGR numpy array (the person bounding-box crop from frame[y1:y2, x1:x2]).
        """
        self._ensure_loaded()
        from PIL import Image
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        result = self._pipe(pil_img)
        if not result or result[0]["score"] < BODY_GENDER_CONFIDENCE:
            return None
        label = result[0]["label"].lower()
        return "Male" if "male" in label else "Female"
```

`DetectionEngine.__init__` gains (after existing tracker initialisation):

```python
from detection import BodyGenderAnalyzer   # add to top-of-file imports
...
self.body_gender = BodyGenderAnalyzer()
```

### 5. `backend/detection.py` — `BodyReIDTracker`

**New attribute in `__init__`:**

```python
self.track_to_person: Dict[int, int] = {}
# ByteTrack track_id → confirmed person_id (fast path, in-memory only)
```

**Updated `check_person` signature** (`track_id` added before existing `gender`/`age`/`age_group`; all existing parameters retained):

```python
def check_person(
    self,
    body_embedding: Optional[np.ndarray],
    track_id: Optional[int] = None,   # NEW: ByteTrack track ID
    gender: Optional[str] = None,
    age: Optional[int] = None,
    age_group: Optional[str] = None,
) -> Tuple[bool, int]:
```

`age_group` is **retained** — it flows through `_promote()` and stats attribution unchanged.

**Logic changes inside `check_person`:**

1. **Fast path** — at the top of the method, before `_evict_expired`:
   ```python
   if track_id is not None and track_id in self.track_to_person:
       return False, self.track_to_person[track_id]
   ```
2. **Pending key** — use `track_id` (int) when available; fall back to a new `uuid.uuid4().hex` string otherwise (unchanged for non-tracked callers).
3. **On confirmation** — after `_promote()` returns `person_id`, store:
   ```python
   if track_id is not None:
       self.track_to_person[track_id] = person_id
   ```

**`_evict_expired()` interaction** — `_evict_expired()` (line 1144) already evicts stale persons from `self.persons` by timestamp. It does **not** touch `track_to_person`. The new `clear_track()` handles `track_to_person` eviction; `_evict_expired()` remains unchanged.

**New helper:**

```python
def clear_track(self, track_id: int) -> None:
    """Called when ByteTrack signals a track has permanently ended."""
    self.track_to_person.pop(track_id, None)
    self.pending.pop(track_id, None)
```

### 6. `backend/streaming.py` — `StreamManager._stream_loop`

**Frame-interval strategy change:**

ByteTrack requires `persist=True` to maintain track continuity; this only works correctly when `track()` is called on **every frame**. Therefore:

- `detection_interval` is removed — `person_detector.track(frame)` runs every frame.
- `analysis_interval` is **kept** — OSNet embedding + face analysis still runs every 4th frame (heavy computation). Track IDs provide the continuity across non-analysis frames.

**New instance variable** (initialised in `__init__`):

```python
self.prev_track_ids: set = set()
```

**Replacement loop structure:**

```python
frame_counter = 0
analysis_interval = 4   # Run OSNet + face analysis every 4 frames
last_detections: List[Detection] = []

while self.streaming:
    frame = self._read_frame()
    if frame is None:
        continue
    frame_counter += 1
    is_analysis_frame = frame_counter % analysis_interval == 0

    # ByteTrack called every frame for consistent state
    detections = self.detection_engine.person_detector.track(frame)

    current_track_ids: set = set()

    for det in detections:
        x1, y1, x2, y2 = det.bbox
        w, h = x2 - x1, y2 - y1

        # 1. Min-size filter — must pass before adding to current_track_ids
        if w < MIN_PERSON_W or h < MIN_PERSON_H:
            continue

        current_track_ids.add(det.track_id)

        # 2. Fast path: track already confirmed
        #    Face/person capture tiles are NOT re-saved on fast path (captured at confirmation).
        #    Re-uses existing "emit detection to WS" path for confirmed persons.
        if det.track_id is not None and det.track_id in self.detection_engine.body_tracker.track_to_person:
            person_id = self.detection_engine.body_tracker.track_to_person[det.track_id]
            # (emit WS detection event for person_id — same code path as confirmed persons below)
            continue

        # 3. Heavy analysis only on analysis frames
        if not is_analysis_frame:
            continue

        # 4. OSNet body embedding (full frame + bbox — existing signature)
        body_emb = self.detection_engine.osnet.extract(frame, det.bbox)
        if body_emb is None and self.detection_engine.osnet.available:
            continue   # crop too small for OSNet, skip

        gender, age, age_group = None, None, None

        # 5. Face + gender analysis (gated on enable_gender — same as current code)
        if self.detection_engine.enable_gender:
            analysis = self.detection_engine.face_analyzer.analyze(frame, det.bbox)
            gender    = analysis.get("gender")
            age       = analysis.get("age")
            age_group = analysis.get("age_group")

            # 6. Body-gender fallback (only when enable_gender is True)
            if gender is None or gender == "Unknown":
                crop = frame[y1:y2, x1:x2]
                gender = self.detection_engine.body_gender.predict(crop)

        # 7. Re-ID / count
        is_new, person_id = self.detection_engine.body_tracker.check_person(
            body_emb,
            track_id=det.track_id,
            gender=gender,
            age=age,
            age_group=age_group,
        )
        # ... existing WS broadcast, face/person capture save logic unchanged ...

    # 8. Clear stale tracks — only after ByteTrack has permanently dropped them
    #    Because track() is called every frame, a track absent this frame is
    #    truly gone (ByteTrack's internal lost-track TTL has expired).
    for gone_id in (self.prev_track_ids - current_track_ids):
        if gone_id is not None:
            self.detection_engine.body_tracker.clear_track(gone_id)
    self.prev_track_ids = current_track_ids
```

**`person_detector.detect(frame)`** calls in the loop are replaced with `person_detector.track(frame)`. The `/capture` snapshot path in a separate route handler keeps `detect()` unchanged.

---

## Data Flow Summary

```
frame (every frame)
  → PersonDetector.track(frame, device=0, half=True)  → List[Detection(track_id=N)]
  → min-size filter (W<50 or H<100 → skip; add to current_track_ids only after passing)
  → fast-path check (track_id confirmed → emit WS, skip heavy work)
  → [analysis_interval] OSNet.extract(frame, bbox)    → body_emb (None = too small → skip)
  → [enable_gender]    FaceAnalyzer.analyze(frame, bbox) → {gender, age, age_group}
  → [enable_gender]    BodyGenderAnalyzer.predict(crop_bgr) → gender fallback
  → BodyReIDTracker.check_person(body_emb, track_id, gender, age, age_group)
  → WS broadcast                                       → dashboard update
  → [end of frame] clear_track() for disappeared track_ids
```

---

## Config Changes

| Key | Default | Description |
|-----|---------|-------------|
| `MIN_PERSON_W` | 50 | Min crop width in pixels |
| `MIN_PERSON_H` | 100 | Min crop height in pixels |
| `BODY_GENDER_CONFIDENCE` | 0.70 | Body gender classifier min confidence |

---

## Dependencies

- `ultralytics >= 8.0` — already installed; ByteTrack bundled as `bytetrack.yaml`.
- `transformers>=4.35` — **add to `requirements.txt`** (not currently present).
- `torch` — already installed (CPU mode used for BodyGenderAnalyzer).
- `Pillow` — already installed (used by transformers pipeline).

---

## Testing Strategy

1. **Unit — min-size filter**: assert detections with W<50 or H<100 are dropped *before* being added to `current_track_ids` and before any OSNet/face analysis call.
2. **Unit — fast path**: mock `track_to_person = {5: 42}`; call `check_person(emb, track_id=5)`; assert returns `(False, 42)` and no cosine computation occurred.
3. **Unit — `clear_track`**: assert `track_id` is removed from both `track_to_person` and `pending` maps after call.
4. **Unit — `BodyGenderAnalyzer`**: mock the HF pipeline; assert "Male"/"Female" returned above `BODY_GENDER_CONFIDENCE`, `None` returned below threshold.
5. **Unit — `OSNet.extract` calling convention**: assert that the streaming path calls `osnet.extract(full_frame, bbox_tuple)` with both arguments, not `osnet.extract(crop)`, to prevent regression.
6. **Unit — body-gender skipped when `enable_gender=False`**: assert `BodyGenderAnalyzer.predict` is never called when `detection_engine.enable_gender = False`.
7. **Integration — no count inflation**: feed a sequence of tiny (20×30 px) bboxes via mocked `track()` with OSNet available; assert `stats["total_visitors"]` stays at 0.
8. **Integration — track confirmation**: feed 4 frames with the same `track_id` and a valid embedding; assert person is confirmed after `body_tracker.confirmation_count` detections and `track_to_person[track_id]` is set.
9. **Integration — track eviction**: assert that when a `track_id` disappears from the next frame's `track()` output, `clear_track` removes it from both `track_to_person` and `pending`.

---

## Migration / Backwards Compatibility

- `detect()` on `PersonDetector` is **kept** for the `/capture` snapshot API endpoint.
- `track_to_person` is **in-memory only** — not persisted. It is rebuilt from scratch on restart (ByteTrack IDs are session-local integers, not globally unique).
- `check_person(track_id=None, ...)` default keeps existing callers (tests, snapshot capture) working without modification.
- Existing unit tests for `BodyReIDTracker` pass no `track_id` argument and remain valid.
- `_evict_expired()` is **unchanged**; `clear_track()` is a complementary eviction path for within-session track lifecycle only.
