# Face Capture Panel Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live face capture panel to the dashboard right column that shows the last 20 face crops with gender/age/visitor info, stored on disk for 24 hours, pushed in real-time via the existing WebSocket.

**Architecture:** A new `face_capture_store.py` module handles all disk I/O and index management independently. `streaming.py` calls it after face analysis and broadcasts a `face_capture` WS message. `main.py` adds two REST endpoints and a startup cleanup task. The frontend prepends tiles on WS events and restores from REST on page load.

**Tech Stack:** Python asyncio, FastAPI, OpenCV (crop/encode), JSON index file, vanilla JS DOM methods, CSS keyframe animations.

**Spec:** `docs/superpowers/specs/2026-03-11-face-capture-panel-design.md`

---

## Chunk 1: Face Capture Store

### Task 1: Create `face_capture_store.py`

**Files:**
- Create: `backend/face_capture_store.py`
- Create: `tests/test_face_capture_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_face_capture_store.py`:

```python
"""Tests for FaceCaptureStore — disk I/O, throttling, cleanup, index management."""

import json
import time
import pytest
import numpy as np
from pathlib import Path


@pytest.fixture
def store(tmp_path):
    """FaceCaptureStore pointing at a temp directory."""
    from face_capture_store import FaceCaptureStore
    return FaceCaptureStore(capture_dir=str(tmp_path))


def make_frame(h=480, w=640):
    return np.zeros((h, w, 3), dtype=np.uint8)


def make_analysis(gender="Male", age=28, age_group="Young Adults"):
    return {
        "gender": gender,
        "age": age,
        "age_group": age_group,
        "gender_confidence": 0.9,
        "embedding": np.zeros(512),
    }


# ---------------------------------------------------------------------------
# save_capture
# ---------------------------------------------------------------------------

def test_save_capture_creates_jpg(store, tmp_path):
    frame = make_frame()
    record = store.save_capture(frame, (100, 100, 200, 200), make_analysis(), visitor_id=1, is_new_visitor=True)
    assert record is not None
    assert (tmp_path / record["filename"]).exists()
    assert record["filename"].endswith(".jpg")


def test_save_capture_returns_metadata(store):
    record = store.save_capture(make_frame(), (100, 100, 200, 200),
                                make_analysis(gender="Female", age=34, age_group="Adults"),
                                visitor_id=2, is_new_visitor=False)
    assert record["gender"] == "Female"
    assert record["age"] == 34
    assert record["age_group"] == "Adults"
    assert record["visitor_id"] == 2
    assert record["is_new_visitor"] is False
    assert "id" in record and "filename" in record and "timestamp" in record


def test_save_capture_appends_to_index(store, tmp_path):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    store._last_capture_time.clear()
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    index = json.loads((tmp_path / "index.json").read_text())
    assert len(index) == 2


def test_save_capture_bbox_clamped_to_frame(store, tmp_path):
    """Bbox extending beyond frame dimensions must be clamped — no crash."""
    record = store.save_capture(make_frame(h=100, w=100), (80, 80, 200, 200),
                                make_analysis(), visitor_id=None, is_new_visitor=False)
    assert record is not None
    assert (tmp_path / record["filename"]).exists()


def test_save_capture_unknown_gender_skipped(store, tmp_path):
    """Unknown gender must not be saved."""
    record = store.save_capture(make_frame(), (50, 50, 150, 150),
                                make_analysis(gender="Unknown"), visitor_id=None, is_new_visitor=False)
    assert record is None
    assert not (tmp_path / "index.json").exists()


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------

def test_throttle_blocks_same_visitor_within_30s(store):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=5, is_new_visitor=False)
    record = store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=5, is_new_visitor=False)
    assert record is None


def test_throttle_allows_same_visitor_after_30s(store):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=6, is_new_visitor=False)
    store._last_capture_time[("visitor", 6)] -= 31
    record = store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=6, is_new_visitor=False)
    assert record is not None


def test_throttle_unconfirmed_keyed_by_bbox_centre(store):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    # Same quantised centre
    record = store.save_capture(make_frame(), (52, 52, 148, 148), make_analysis(), visitor_id=None, is_new_visitor=False)
    assert record is None


# ---------------------------------------------------------------------------
# get_recent
# ---------------------------------------------------------------------------

def test_get_recent_returns_newest_first(store):
    for _ in range(5):
        store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
        store._last_capture_time.clear()
    records = store.get_recent(limit=5)
    timestamps = [r["timestamp"] for r in records]
    assert timestamps == sorted(timestamps, reverse=True)


def test_get_recent_respects_limit(store):
    for _ in range(25):
        store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
        store._last_capture_time.clear()
    assert len(store.get_recent(limit=20)) <= 20


# ---------------------------------------------------------------------------
# cleanup_expired
# ---------------------------------------------------------------------------

def test_cleanup_removes_files_older_than_24h(store, tmp_path):
    record = store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    # Backdate to 25 hours ago
    index_path = tmp_path / "index.json"
    index = json.loads(index_path.read_text())
    index[0]["timestamp"] = time.time() - (25 * 3600)
    index_path.write_text(json.dumps(index))

    assert store.cleanup_expired() == 1
    assert not (tmp_path / record["filename"]).exists()
    assert len(json.loads(index_path.read_text())) == 0


def test_cleanup_keeps_files_within_24h(store, tmp_path):
    store.save_capture(make_frame(), (50, 50, 150, 150), make_analysis(), visitor_id=None, is_new_visitor=False)
    assert store.cleanup_expired() == 0
    assert len(json.loads((tmp_path / "index.json").read_text())) == 1
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /home/adilhidayat/visitor-analytics
venv/bin/pytest tests/test_face_capture_store.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'face_capture_store'`

- [ ] **Step 3: Implement `face_capture_store.py`**

Create `backend/face_capture_store.py`:

```python
"""Face capture storage: save crops to disk, manage 24h index, throttle duplicates."""

import cv2
import json
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

PADDING = 30
JPEG_QUALITY = 85
THROTTLE_SECONDS = 30
GRID_SIZE = 50  # px quantisation for unconfirmed bbox throttle key


class FaceCaptureStore:
    """Save face crops to disk and maintain a 24-hour rolling index."""

    def __init__(self, capture_dir: str):
        self.capture_dir = capture_dir
        os.makedirs(capture_dir, exist_ok=True)
        self._index_path = os.path.join(capture_dir, "index.json")
        self._last_capture_time: Dict[Tuple, float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_capture(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        analysis: dict,
        visitor_id: Optional[int],
        is_new_visitor: bool,
    ) -> Optional[dict]:
        """Crop, save and index a face capture. Returns metadata record or None."""
        gender = analysis.get("gender", "Unknown")
        if not gender or gender == "Unknown":
            return None

        throttle_key = self._throttle_key(bbox, visitor_id)
        now = time.time()
        if now - self._last_capture_time.get(throttle_key, 0) < THROTTLE_SECONDS:
            return None
        self._last_capture_time[throttle_key] = now

        crop = self._crop_frame(frame, bbox)
        if crop is None:
            return None

        capture_id = f"{int(now * 1000)}_{uuid.uuid4().hex[:4]}"
        filename = f"{capture_id}.jpg"
        filepath = os.path.join(self.capture_dir, filename)

        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            logger.warning("Failed to encode face crop %s", capture_id)
            return None

        with open(filepath, "wb") as f:
            f.write(buf.tobytes())

        record = {
            "id": capture_id,
            "filename": filename,
            "timestamp": now,
            "gender": gender,
            "age": analysis.get("age"),
            "age_group": analysis.get("age_group", "Unknown"),
            "visitor_id": visitor_id,
            "is_new_visitor": is_new_visitor,
        }
        self._append_index(record)
        return record

    def get_recent(self, limit: int = 20) -> List[dict]:
        """Return up to `limit` records, newest first."""
        index = self._load_index()
        index.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return index[:limit]

    def cleanup_expired(self, max_age_seconds: float = 86400) -> int:
        """Delete files and index entries older than max_age_seconds."""
        now = time.time()
        index = self._load_index()
        kept, deleted_count = [], 0

        for record in index:
            if now - record.get("timestamp", 0) >= max_age_seconds:
                try:
                    os.remove(os.path.join(self.capture_dir, record["filename"]))
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

    def _throttle_key(self, bbox: Tuple, visitor_id: Optional[int]) -> Tuple:
        if visitor_id is not None:
            return ("visitor", visitor_id)
        x1, y1, x2, y2 = bbox
        cx = round(((x1 + x2) / 2) / GRID_SIZE) * GRID_SIZE
        cy = round(((y1 + y2) / 2) / GRID_SIZE) * GRID_SIZE
        return ("bbox", cx, cy)

    def _crop_frame(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1 = max(0, x1 - PADDING)
        y1 = max(0, y1 - PADDING)
        x2 = min(w, x2 + PADDING)
        y2 = min(h, y2 + PADDING)
        if x2 <= x1 or y2 <= y1:
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

- [ ] **Step 4: Run tests — all must pass**

```bash
cd /home/adilhidayat/visitor-analytics
venv/bin/pytest tests/test_face_capture_store.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add backend/face_capture_store.py tests/test_face_capture_store.py
git commit -m "feat: add FaceCaptureStore with disk persistence, throttling and 24h cleanup"
```

---

## Chunk 2: Streaming Integration

### Task 2: Wire FaceCaptureStore into the stream loop

**Files:**
- Modify: `backend/streaming.py`

- [ ] **Step 1: Add import and store init**

Add at the top of `backend/streaming.py` (with existing imports):

```python
import os
from face_capture_store import FaceCaptureStore
```

In `StreamManager.__init__`, after the existing assignments add:

```python
        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.face_store = FaceCaptureStore(
            capture_dir=os.path.join(_project_root, "backend", "data", "face_captures")
        )
```

- [ ] **Step 2: Add `_broadcast_face_capture` helper method**

Add after `reset_session_stats` in `StreamManager`:

```python
    async def _broadcast_face_capture(self, record: dict) -> None:
        """Broadcast a face_capture event to all connected WebSocket clients."""
        import json as _json
        message = _json.dumps({
            "type": "face_capture",
            "data": {
                "id": record["id"],
                "url": f"/faces/{record['filename']}",
                "timestamp": record["timestamp"],
                "gender": record["gender"],
                "age": record["age"],
                "age_group": record["age_group"],
                "visitor_id": record["visitor_id"],
                "is_new_visitor": record["is_new_visitor"],
            }
        })
        await self.connection_manager.broadcast_frame(message)
```

- [ ] **Step 3: Call store after face analysis in `_stream_loop`**

Find the loop that writes analysis results onto detections:

```python
                        for det, analysis in zip(detections, analyses):
                            det.gender = analysis["gender"]
                            ...
                            det.embedding = analysis["embedding"]
```

Immediately after that block (still inside `if self.detection_engine.enable_gender and is_analysis_frame:`), add:

```python
                            # Save face crop when gender is known
                            if analysis.get("gender") and analysis["gender"] != "Unknown":
                                record = self.face_store.save_capture(
                                    resized_frame,
                                    det.bbox,
                                    analysis,
                                    visitor_id=det.visitor_id,
                                    is_new_visitor=det.is_new_visitor,
                                )
                                if record:
                                    await self._broadcast_face_capture(record)
```

- [ ] **Step 4: Smoke-test**

```bash
echo '4$$p4r4d3' | sudo -S systemctl restart visitor-analytics.service
sleep 5
journalctl -u visitor-analytics.service -n 20 --no-pager | grep -i "error\|face_capture"
```

Expected: service starts cleanly, no import errors.

- [ ] **Step 5: Commit**

```bash
git add backend/streaming.py
git commit -m "feat: save face crops and broadcast face_capture WS event after analysis"
```

---

## Chunk 3: API Endpoints & Cleanup Task

### Task 3: Add `/faces` endpoints and hourly cleanup to `main.py`

**Files:**
- Modify: `backend/main.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to the end of `tests/test_api.py`:

```python
# ---------------------------------------------------------------------------
# Face capture endpoints
# ---------------------------------------------------------------------------

class TestFaceEndpoints:
    def test_get_faces_returns_list(self, client):
        with patch("main.stream_manager") as mock_sm:
            mock_sm.face_store.get_recent.return_value = []
            resp = client.get("/faces", headers={"X-API-Key": "test-secret-key"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_faces_requires_auth(self, client):
        resp = client.get("/faces")
        assert resp.status_code == 401

    def test_get_faces_includes_url_field(self, client):
        fake = {
            "id": "abc123", "filename": "abc123.jpg",
            "timestamp": 1000.0, "gender": "Male", "age": 28,
            "age_group": "Young Adults", "visitor_id": 1, "is_new_visitor": False,
        }
        with patch("main.stream_manager") as mock_sm:
            mock_sm.face_store.get_recent.return_value = [fake]
            resp = client.get("/faces", headers={"X-API-Key": "test-secret-key"})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["url"] == "/faces/abc123.jpg"

    def test_get_face_image_not_found(self, client):
        resp = client.get("/faces/nonexistent.jpg", headers={"X-API-Key": "test-secret-key"})
        assert resp.status_code == 404

    def test_get_face_image_rejects_path_traversal(self, client):
        resp = client.get("/faces/..%2Fsecret.txt", headers={"X-API-Key": "test-secret-key"})
        assert resp.status_code in (400, 404)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
venv/bin/pytest tests/test_api.py::TestFaceEndpoints -v 2>&1 | head -20
```

Expected: `FAILED` — endpoints don't exist yet.

- [ ] **Step 3: Add imports to `main.py`**

Add `import re` to the top-level imports in `backend/main.py`.

Add `from face_capture_store import FaceCaptureStore` with the other local imports.

- [ ] **Step 4: Add the two endpoints to `main.py`**

Insert after the `/proxy.pac` route:

```python
@app.get("/faces", dependencies=[Depends(require_auth)])
async def list_faces():
    """Return the last 20 face captures, newest first."""
    records = stream_manager.face_store.get_recent(limit=20)
    for r in records:
        r["url"] = f"/faces/{r['filename']}"
    return records


@app.get("/faces/{filename}", dependencies=[Depends(require_auth)])
async def get_face_image(filename: str):
    """Serve a face capture JPEG."""
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+\.jpg", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "backend", "data", "face_captures", filename,
    )
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")
```

- [ ] **Step 5: Add cleanup background task in `lifespan`**

Inside the `lifespan` async context manager, after `await stream_manager.start_streaming()`, add:

```python
        async def _face_cleanup_loop():
            while True:
                await asyncio.sleep(3600)
                try:
                    deleted = stream_manager.face_store.cleanup_expired()
                    if deleted:
                        logger.info("Face capture cleanup: deleted %d expired files", deleted)
                except Exception as e:
                    logger.error("Face capture cleanup error: %s", e)

        asyncio.create_task(_face_cleanup_loop())
```

- [ ] **Step 6: Run all API tests**

```bash
venv/bin/pytest tests/test_api.py -v 2>&1 | tail -20
```

Expected: all pass including new `TestFaceEndpoints`.

- [ ] **Step 7: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat: add /faces REST endpoints and hourly 24h cleanup task"
```

---

## Chunk 4: Frontend — CSS & HTML Panel

### Task 4: Add face captures panel to the dashboard

**Files:**
- Modify: `static/css/style.css`
- Modify: `frontend/index.html`

- [ ] **Step 1: Append panel CSS to `static/css/style.css`**

```css
/* =========================================================
   Face Captures Panel
   ========================================================= */
.face-captures-panel {
    background: var(--surface, #1e2130);
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
}

.face-captures-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.75rem;
}

.face-captures-header h3 {
    font-size: 0.85rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-secondary, #8892a4);
    margin: 0;
}

.face-capture-count {
    font-size: 0.7rem;
    background: var(--accent, #3b82f6);
    color: #fff;
    border-radius: 999px;
    padding: 0.15rem 0.55rem;
    font-weight: 600;
}

.face-captures-body {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    overflow: hidden;
    max-height: 440px;
}

.face-captures-empty {
    color: var(--text-secondary, #8892a4);
    font-size: 0.78rem;
    text-align: center;
    padding: 1rem 0;
}

.face-tile {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    background: var(--surface-2, #252a3a);
    border-radius: 8px;
    padding: 0.4rem 0.5rem;
    border-left: 3px solid transparent;
    animation: face-tile-in 0.2s ease-out;
    flex-shrink: 0;
}

@keyframes face-tile-in {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
}

.face-tile.male   { border-left-color: #3b82f6; }
.face-tile.female { border-left-color: #ec4899; }

.face-tile-img {
    width: 48px;
    height: 64px;
    object-fit: cover;
    border-radius: 4px;
    flex-shrink: 0;
    background: var(--surface, #1e2130);
}

.face-tile-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
}

.face-tile-gender {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--text-primary, #e2e8f0);
}

.face-tile-age {
    font-size: 0.72rem;
    color: var(--text-secondary, #8892a4);
}

.face-tile-visitor {
    font-size: 0.7rem;
    color: var(--text-secondary, #8892a4);
}

.face-tile-time {
    font-size: 0.68rem;
    color: var(--text-tertiary, #64748b);
}

.face-new-badge {
    font-size: 0.62rem;
    font-weight: 700;
    background: #10b981;
    color: #fff;
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    margin-left: 0.25rem;
    vertical-align: middle;
}

.face-unconfirmed {
    color: var(--text-tertiary, #64748b);
    font-style: italic;
}
```

- [ ] **Step 2: Add HTML panel to `index.html`**

Find `<!-- Gender Distribution -->` in the `<aside class="stats-section">`. Insert the panel **immediately before** it:

```html
                <!-- Face Captures -->
                <div class="stats-card face-captures-panel">
                    <div class="face-captures-header">
                        <h3>Face Captures</h3>
                        <span class="face-capture-count" id="face-capture-count">0</span>
                    </div>
                    <div class="face-captures-body" id="face-captures-body">
                        <div class="face-captures-empty" id="face-captures-empty">No faces detected yet</div>
                    </div>
                </div>
```

- [ ] **Step 3: Verify panel renders**

```bash
echo '4$$p4r4d3' | sudo -S systemctl restart visitor-analytics.service
```

Open `https://172.31.0.250` — confirm "Face Captures" panel appears with empty placeholder. No console errors.

- [ ] **Step 4: Commit**

```bash
git add static/css/style.css frontend/index.html
git commit -m "feat: add face captures panel HTML and CSS to dashboard"
```

---

## Chunk 5: Frontend — JavaScript Logic

### Task 5: Wire up panel JS

**Files:**
- Modify: `frontend/index.html` (inline `<script>` block)

All tile construction uses safe DOM methods — no `innerHTML` — to prevent XSS.

- [ ] **Step 1: Add `buildFaceTile(capture)` helper**

In the `<script>` block, add after variable declarations:

```javascript
function buildFaceTile(capture) {
    const tile = document.createElement('div');
    tile.className = 'face-tile ' + (capture.gender === 'Male' ? 'male' : 'female');

    const img = document.createElement('img');
    img.className = 'face-tile-img';
    img.src = capture.url;
    img.alt = 'Face';
    img.onerror = function() { this.style.opacity = '0.3'; };

    const info = document.createElement('div');
    info.className = 'face-tile-info';

    const genderEl = document.createElement('div');
    genderEl.className = 'face-tile-gender';
    genderEl.textContent = capture.gender;

    const ageEl = document.createElement('div');
    ageEl.className = 'face-tile-age';
    ageEl.textContent = capture.age != null
        ? capture.age + 'y \u00B7 ' + (capture.age_group || '')
        : (capture.age_group || '');

    const visitorEl = document.createElement('div');
    visitorEl.className = 'face-tile-visitor';
    if (capture.visitor_id != null) {
        visitorEl.textContent = 'Visitor #' + capture.visitor_id;
        if (capture.is_new_visitor) {
            const badge = document.createElement('span');
            badge.className = 'face-new-badge';
            badge.textContent = 'NEW';
            visitorEl.appendChild(badge);
        }
    } else {
        visitorEl.textContent = 'Unconfirmed';
        visitorEl.classList.add('face-unconfirmed');
    }

    const timeEl = document.createElement('div');
    timeEl.className = 'face-tile-time';
    timeEl.textContent = new Date(capture.timestamp * 1000).toLocaleTimeString();

    info.appendChild(genderEl);
    info.appendChild(ageEl);
    info.appendChild(visitorEl);
    info.appendChild(timeEl);
    tile.appendChild(img);
    tile.appendChild(info);
    return tile;
}

function prependFaceTile(capture) {
    const body = document.getElementById('face-captures-body');
    const empty = document.getElementById('face-captures-empty');
    if (empty) empty.remove();

    body.insertBefore(buildFaceTile(capture), body.firstChild);

    // Rolling window: keep max 20 tiles
    while (body.children.length > 20) {
        body.removeChild(body.lastChild);
    }

    const counter = document.getElementById('face-capture-count');
    if (counter) counter.textContent = parseInt(counter.textContent || '0') + 1;
}
```

- [ ] **Step 2: Add `loadFaceCaptures()` for page-load restore**

```javascript
async function loadFaceCaptures() {
    try {
        const resp = await fetch('/faces');
        if (!resp.ok) return;
        const captures = await resp.json();
        // API returns newest-first; reverse so prepend builds correct top-to-bottom order
        [...captures].reverse().forEach(prependFaceTile);
    } catch (e) {
        console.warn('Could not load face captures:', e);
    }
}
```

- [ ] **Step 3: Call `loadFaceCaptures()` on page load**

Find the existing `DOMContentLoaded` or `window.onload` handler and add:

```javascript
    loadFaceCaptures();
```

If no such handler exists, add a new one at the bottom of the script block:

```javascript
document.addEventListener('DOMContentLoaded', loadFaceCaptures);
```

- [ ] **Step 4: Handle `face_capture` WS messages**

Find the existing WebSocket `onmessage` handler where `data.type` is checked. Add:

```javascript
        } else if (data.type === 'face_capture') {
            prependFaceTile(data.data);
        }
```

- [ ] **Step 5: End-to-end smoke test**

```bash
echo '4$$p4r4d3' | sudo -S systemctl restart visitor-analytics.service
```

1. Open `https://172.31.0.250`
2. Walk close to the camera so a face is visible in the frame
3. Confirm a tile appears in the Face Captures panel with gender, age, timestamp
4. Refresh the page — confirm tile is restored from `GET /faces`
5. Check browser console for errors — expect none

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html
git commit -m "feat: wire face capture panel JS — real-time WS tiles and page-load restore"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
cd /home/adilhidayat/visitor-analytics
venv/bin/pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Add `face_captures/` to `.gitignore`**

```bash
grep "face_captures" .gitignore || echo "backend/data/face_captures/" >> .gitignore
git add .gitignore
git commit -m "chore: ignore face capture images from git"
```
