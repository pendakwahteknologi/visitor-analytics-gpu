# Body Re-ID Unique Visitor Tracking — Design Spec

**Date:** 2026-03-11
**Status:** Approved

---

## Overview

Add whole-body appearance-based re-identification (Re-ID) as the primary mechanism for counting unique visitors. The existing gender/age detection pipeline is unchanged — it provides enrichment data that gets attached to body-tracked person records. One person = one count, with gender/age filled in when the face is visible.

A new "Person Captures" panel (above Face Captures) displays body crop tiles for each confirmed unique individual.

---

## Problem Statement

The current `VisitorTracker` counts unique visitors using face embeddings and requires gender to be confirmed. This means:
- People whose faces aren't clearly visible are not counted
- The unique visitor count is artificially low in top-down or angled camera setups
- Gender and unique-person counts are effectively conflated

---

## Goals

- Count unique individuals using whole-body appearance (OSNet Re-ID model)
- Attribute gender/age to body-tracked persons when detectable
- Display body crop tiles in a new "Person Captures" panel
- 24-hour rolling storage for body crops
- No changes to existing gender/age detection logic or FaceCaptureStore

---

## Non-Goals

- Replacing InsightFace or DeepFace for gender/age detection
- Changing the Face Captures panel or `/faces` endpoint
- Cross-session persistent identity (visitors cleared on service restart after state recovery)

---

## Architecture

### New Components

#### 1. `OSNetAnalyzer` (in `detection.py`)
- Loads OSNet-x1.0 weights from torchreid (see Dependency section)
- Input: tight body crop taken from the **resized 1280px frame** at the raw YOLO bbox coordinates (no padding). Crop is letterboxed (not stretched) to 256×128 px preserving aspect ratio with black fill before inference.
- Output: 512-dim L2-normalised embedding vector
- Runs on GPU (CUDA) with CPU fallback
- Called at the same 4-frame analysis interval as InsightFace
- If init fails (model not found, download error): logs a warning, sets `self.available = False`. `BodyReIDTracker` then operates in count-only mode: the confirmation threshold is bypassed (every person is confirmed immediately on first detection with no pending stage), so `total_visitors` reflects a cumulative frame-level count rather than a de-duplicated unique count. This is a graceful degradation — the system remains functional, just less accurate.
- If inference throws on a single frame: log warning, return `None`. Caller skips body Re-ID for that detection.
- Body crop smaller than 32×32 px: return `None` silently.

#### 2. `BodyReIDTracker` (in `detection.py`)
Replaces `VisitorTracker` as the authoritative source for `total_visitors` and gender/age breakdown. `VisitorTracker` is **retired** — it is removed from `DetectionEngine` and `StreamManager`. The face re-ID that previously lived in `VisitorTracker` is no longer needed; `PersonCaptureStore` uses the `person_id` from `BodyReIDTracker` directly.

**Person ID lifecycle:**
- Pending: record held under a UUID key in `self.pending`. `check_person` returns `(False, None)` while pending.
- Confirmed: promoted to `self.persons` with an integer `person_id` (auto-incrementing from 1). `check_person` returns `(True, person_id)` on the promotion frame, and `(False, person_id)` on subsequent sightings.

**`check_person(body_embedding, gender=None, age=None, age_group=None) → (is_confirmed_new, person_id_or_None)`**
- Accepts optional gender/age arguments. These are accumulated on both pending and confirmed records so that gender attribution is not lost if the face is visible before or during confirmation.
- On confirmation: median age from all observations, majority-vote gender from all observations.
- Match threshold: cosine similarity ≥ 0.60 against confirmed persons. For pending persons: ≥ 0.55 (more lenient, gathering observations).
- Confirmation threshold: 3 detections within `pending_timeout=30.0` seconds.
- Memory duration: 1800 seconds (30 minutes inactivity → evict).
- Max active persons: 500 (LRU eviction).
- Exposes `stats` dict: `total_visitors`, `male`, `female`, `unknown`, `age_groups` — updated on every confirmation and on every `attach_gender` call for confirmed persons.

**`attach_gender(person_id, gender, age, age_group)`**
- Updates gender/age on an already-confirmed person record.
- Recalculates `self.stats` gender/age counts.
- Used when InsightFace detects a gender on a frame after the person was already confirmed.

**`reset()`** — clears all state and resets stats to zero. Called by `StreamManager.reset_session_stats()`.

**State persistence:**
- `BodyReIDTracker` participates in the same `VisitorStatePersistence` save/restore cycle as the retired `VisitorTracker`. `VisitorStatePersistence` is updated with a new signature:
  - `save_state(persons, pending, stats, next_person_id)` — replaces the old `save_state(visitors, pending_visitors, stats, next_visitor_id, next_pending_id)`. `next_pending_id` is dropped because pending records use UUID keys (not integers).
  - `restore_state() → (persons, pending, stats, next_person_id)` — returns the same four fields.
- Auto-saves every 30 seconds; restored on startup. Embeddings encrypted at-rest if `EMBEDDING_ENCRYPTION_KEY` is set.

#### 3. `PersonCaptureStore` (new `backend/person_capture_store.py`)
- Identical pattern to `FaceCaptureStore`.
- Saves full-body JPEG crops (from the resized 1280px frame, raw YOLO bbox, no padding) to `backend/data/person_captures/`.
- Rolling 24-hour index at `backend/data/person_captures/index.json`.
- Throttle: one save per `person_id` per 30 seconds (allows crop to be refreshed as person moves, same intent as `FaceCaptureStore`).
- `save_capture(frame, bbox, person_id, gender, age, age_group, is_new) → Optional[dict]` — saves on every call that passes the throttle (not only on `is_new=True`). `is_new=True` is passed only on the promotion frame (when `check_person` returns `(True, person_id)`); all subsequent throttle-allowed crop refreshes pass `is_new=False`. `is_new` is stored in the record for frontend display.
- `get_recent(limit=20)` → list of records newest-first.
- `cleanup_expired(max_age_seconds=86400)` → deletes old files and index entries.

#### 4. `/persons` REST Endpoints and `person_capture` WebSocket Event

```python
@app.get("/persons", dependencies=[Depends(require_auth)])
async def get_persons(limit: int = 20):
    ...

@app.get("/persons/{filename}", dependencies=[Depends(require_auth)])
async def get_person_image(filename: str):
    ...
```

Both endpoints require auth (`require_auth` dependency), consistent with `/faces`.

**Note on WS field naming:** The `person_capture` event uses `person_id` (not `visitor_id` as in `face_capture`). The frontend JavaScript must handle both field names in its respective WS handlers — `message.data.visitor_id` for face captures and `message.data.person_id` for person captures.

`person_capture` WebSocket message schema:
```json
{
  "type": "person_capture",
  "data": {
    "id": "1773211264713_bb95",
    "filename": "1773211264713_bb95.jpg",
    "timestamp": 1773211264.713,
    "gender": "Male",
    "age": 34,
    "age_group": "Adults",
    "person_id": 7,
    "is_new": true,
    "url": "/persons/1773211264713_bb95.jpg"
  }
}
```

#### 5. Hourly Cleanup Task
- `cleanup_persons_task` in `main.py` calls `PersonCaptureStore.cleanup_expired()` every hour (same pattern as face captures).

### Modified Components

#### `detection.py` — `DetectionEngine`
- Add `OSNetAnalyzer` instance.
- Remove `VisitorTracker`. `BodyReIDTracker` replaces it.
- `get_visitor_stats()` returns `self.body_tracker.stats`.
- `reset_visitor_stats()` calls `self.body_tracker.reset()`.

#### `streaming.py` — `StreamManager`
- Instantiates `PersonCaptureStore`.
- In `_stream_loop`, on analysis frames (every 4 frames):
  1. For each detection, extract body crop from resized frame at raw YOLO bbox.
  2. Run `OSNetAnalyzer.extract(body_crop)` → `body_embedding` (or `None`).
  3. If `body_embedding` is not None: call `BodyReIDTracker.check_person(body_embedding, gender, age, age_group)` — pass gender/age from InsightFace if available in the same frame (run InsightFace first in the loop).
  4a. If result is `(True, person_id)` (confirmed new): call `PersonCaptureStore.save_capture(..., is_new=True)`. If a record is returned, broadcast `person_capture` WS event.
  4b. If result is `(False, person_id)` and `person_id is not None` (already confirmed, seen again) and throttle allows: call `PersonCaptureStore.save_capture(..., is_new=False)` to refresh the crop.
  5. If result is `(False, person_id)` and `person_id is not None`: call `BodyReIDTracker.attach_gender(person_id, gender, age, age_group)` when gender is known.
- `reset_session_stats()` calls `self.detection_engine.reset_visitor_stats()` (which now resets `BodyReIDTracker`). No other change needed here.

#### `main.py`
- Add `/persons` and `/persons/{filename}` endpoints with auth.
- Add hourly `cleanup_persons_task`.
- Update `/health` endpoint to include `osnet_loaded: bool` alongside `insightface_loaded`.
- Update `_handle_shutdown_signal` and the lifespan shutdown handler: replace the two existing `detection_engine.visitor_tracker.save_state(...)` call sites with `detection_engine.body_tracker.save_state(...)` using the new four-parameter signature. These are the only two direct references to `visitor_tracker` in `main.py` and will raise `AttributeError` at shutdown if not updated.

#### `data_storage.py`
- `save_current_stats()` receives stats from `BodyReIDTracker` — schema unchanged (same column names). No code change needed beyond the caller in `streaming.py` using `BodyReIDTracker.stats`.

#### `visitor_state.py` — `VisitorStatePersistence`
- Replace `VisitorTracker` serialization with `BodyReIDTracker` serialization.
- Updated API:
  - `save_state(persons, pending, stats, next_person_id)` — four positional parameters matching `BodyReIDTracker` fields.
  - `restore_state() → (persons, pending, stats, next_person_id)` — returns the same four fields as a tuple.

### Frontend

#### New "Person Captures" Panel (`frontend/index.html`)
- Placed **above** the existing Face Captures panel.
- Same tile grid design as Face Captures.
- Badge counter showing unique persons detected today (from `GET /persons` count on load + WS increments).
- Each tile: body crop image + gender badge (if known) + age label (if known) + "NEW" indicator if `is_new=true`.

#### `static/js/app.js`
- On page load: `GET /persons?limit=20` to restore existing person tiles (same pattern as face captures restore). Does **not** increment the counter during restore (same fix as face captures: `45ff1ec`).
- On `person_capture` WS event: prepend new tile, trim to max 20 tiles, increment counter.
- Counter badge sourced from the running WS tally (not from a separate stat, consistent with face captures).

#### `static/css/style.css`
- Add `.person-captures-panel`, `.person-captures-header`, `.person-captures-body`, `.person-tile` classes.
- Reuse existing face capture tile CSS patterns and colour variables.

---

## Data Flow

```
YOLO detects person bbox (every 2 frames)
    │
    └─► On analysis frame (every 4 frames):
            │
            ├─► InsightFaceAnalyzer.analyze(face_crop) → gender, age, face_embedding [unchanged]
            │       │
            │       └─► FaceCaptureStore.save_capture() [unchanged, still gated on gender != Unknown]
            │           broadcast face_capture WS [unchanged]
            │
            ├─► OSNetAnalyzer.extract(body_crop) → body_embedding
            │
            └─► BodyReIDTracker.check_person(body_embedding, gender, age, age_group)
                    ├─ Still pending → (False, None)
                    ├─ Confirmed new → (True, person_id)
                    │       → PersonCaptureStore.save_capture()
                    │       → broadcast person_capture WS
                    │       → increment total_visitors in BodyReIDTracker.stats
                    └─ Already confirmed, seen again → (False, person_id)
                            → attach_gender if gender known → update gender stats
                            → PersonCaptureStore.save_capture() if throttle allows (refresh crop)
```

---

## Stats Schema (unchanged column names)

```json
{
  "today_saved": {
    "total_visitors": 142,
    "male": 78,
    "female": 52,
    "unknown": 12,
    "age_groups": { "Adults": 85, "Young Adults": 42, ... }
  }
}
```

`total_visitors` now reflects body-tracked unique persons (more inclusive). Gender counts reflect the subset where gender was attributed. The `unknown` count = unique persons with no gender attribution yet.

---

## Storage

| Path | Contents |
|------|----------|
| `backend/data/person_captures/` | Body crop JPEGs |
| `backend/data/person_captures/index.json` | Rolling 24h index |
| `backend/data/face_captures/` | Face crop JPEGs (unchanged) |

---

## Dependency: torchreid + OSNet Weights

- Add `torchreid` to `requirements.txt`.
- On first startup: torchreid downloads OSNet-x1.0 weights (~2MB) from its pretrained registry to `~/.torchreid/` (standard torchreid behaviour).
- If download fails (no internet): `OSNetAnalyzer.__init__` catches the exception, logs a warning, sets `self.available = False`. System continues without body Re-ID (count-only mode: unique visitor count is not available, `total_visitors` falls back to frame-level people count).
- Operators in air-gapped environments should pre-download weights and set `TORCHREID_CACHE_DIR` to a local path.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| OSNet init fails (no internet, missing weights) | `available=False`, count-only mode, warning logged |
| OSNet inference throws | Skip body Re-ID for that detection, warning logged |
| Body crop < 32×32 px | Return `None` silently |
| `VisitorStatePersistence` restore fails | Start fresh (same as existing behaviour) |

---

## `/health` Endpoint Update

Add `osnet_loaded: bool` to the `models` section of the `/health` response:
```json
{
  "status": "ok",
  "models": {
    "yolo_loaded": true,
    "insightface_loaded": true,
    "osnet_loaded": true
  }
}
```

---

## Testing

- Unit test `BodyReIDTracker`:
  - Same person confirmed after 3 detections, `total_visitors` increments once
  - Different persons (dissimilar embeddings) not merged
  - Re-identification after confirmation (person leaves and returns within 30 min)
  - LRU eviction at 500 active persons
  - `attach_gender` updates gender stats correctly and does not double-count
  - Pending timeout expiry: pending record older than 30s is dropped without counting
  - `reset()` clears all state and returns stats to zero
  - Gender accumulated during pending phase is applied at confirmation time
- Unit test `PersonCaptureStore`:
  - save/load/cleanup cycle
  - Throttle prevents saves within 30s per person_id
  - Cleanup deletes files older than 24h
- Integration:
  - `total_visitors` reflects body-tracked count after reset
  - Gender subset is a subset of `total_visitors` (male + female + unknown == total_visitors)
  - `/persons` endpoint returns auth-protected records with correct `url` field
  - `osnet_loaded` reflected correctly in `/health`
