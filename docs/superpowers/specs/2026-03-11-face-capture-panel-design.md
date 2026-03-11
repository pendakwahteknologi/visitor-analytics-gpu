# Face Capture Panel — Design Spec

**Date:** 2026-03-11
**Status:** Approved

## Overview

A live face capture panel on the right side of the dashboard. When InsightFace successfully detects and analyses a face (returning a non-Unknown gender), the face crop is saved to disk and displayed as a tile in the panel. Tiles accumulate as a timeline — up to 20 visible at once, rolling window, newest at top. All captures are auto-deleted after 24 hours.

---

## Data Model & Storage

**Location:** `backend/data/face_captures/`

**Files per capture:**
- `{timestamp_ms}_{uuid4_short}.jpg` — face crop JPEG (bbox + 30px padding, clamped to frame bounds)
- `index.json` — single append-only JSON array of all metadata records in the directory

**Metadata record schema:**
```json
{
  "id": "1741234567123_a3f9",
  "filename": "1741234567123_a3f9.jpg",
  "timestamp": 1741234567.123,
  "gender": "Male",
  "age": 28,
  "age_group": "Young Adults",
  "visitor_id": 3,
  "is_new_visitor": true
}
```

`visitor_id` is `null` for faces that were analysed but not yet confirmed as unique visitors. `is_new_visitor` is `true` only on the frame when a pending visitor is first promoted to confirmed.

**Throttling:** one capture per visitor per 30 seconds. Keyed by `visitor_id` for confirmed visitors, by quantised bbox centre (nearest 50px grid) for unconfirmed. Prevents panel flooding during sustained detections.

**Cleanup:** asyncio background task, runs every hour. Deletes `.jpg` files older than 24 hours and prunes their entries from `index.json`. Uses atomic writes (write to `.tmp`, rename) to avoid corruption.

---

## Backend

### `streaming.py`

New coroutine `_save_face_capture(frame, det, analysis)` called after face analysis returns a non-Unknown gender:

1. Check throttle dict — return early if same person captured within 30s
2. Crop face region: bbox + 30px padding, clamped to frame dimensions
3. `cv2.imencode('.jpg', crop, [cv2.IMWRITE_JPEG_QUALITY, 85])`
4. Write JPEG to `backend/data/face_captures/{id}.jpg`
5. Append metadata record to `index.json` (atomic write)
6. Broadcast `face_capture` WebSocket message via existing `connection_manager`

**WebSocket message format:**
```json
{
  "type": "face_capture",
  "data": {
    "id": "1741234567123_a3f9",
    "url": "/faces/1741234567123_a3f9.jpg",
    "timestamp": 1741234567.123,
    "gender": "Male",
    "age": 28,
    "age_group": "Young Adults",
    "visitor_id": 3,
    "is_new_visitor": true
  }
}
```

### `main.py`

**New endpoints:**

- `GET /faces` — reads `index.json`, returns last 20 records sorted newest-first, with full `/faces/{filename}` URLs. Auth-protected if auth is configured.
- `GET /faces/{filename}` — serves JPEG from `backend/data/face_captures/`. Auth-protected. Validates filename (alphanumeric + `_-.` only) to prevent path traversal.

**New startup task:** `_cleanup_face_captures()` — async loop, sleeps 1 hour between runs, deletes files and index entries older than 24 hours.

---

## Frontend

### Panel placement

New section in the right-side stats column in `index.html`, inserted between "Current Count" and "Gender Distribution".

### Panel structure

```
┌──────────────────────────────────┐
│ Face Captures           [12 today]│
├──────────────────────────────────┤
│ ┌──────────────────────────────┐ │
│ │[img] Male, 28                │ │  ← blue left border
│ │      Young Adults            │ │
│ │      Visitor #3  🟢 NEW      │ │
│ │      13:07:19                │ │
│ └──────────────────────────────┘ │
│ ┌──────────────────────────────┐ │
│ │[img] Female, 34              │ │  ← pink left border
│ │      Adults                  │ │
│ │      Unconfirmed             │ │
│ │      13:06:44                │ │
│ └──────────────────────────────┘ │
│  ... up to 20 tiles ...          │
│                                  │
│  [No faces detected yet]         │  ← empty state
└──────────────────────────────────┘
```

- Face image: 60×80px, object-fit: cover
- Blue left border (3px) for Male, pink for Female
- "NEW VISITOR" badge in accent colour when `is_new_visitor: true`
- Unconfirmed: `visitor_id` null → show "Unconfirmed" in muted text
- Panel body: fixed height, overflow-y hidden (rolling window, no scroll)

### JS logic

Added to existing inline script in `index.html`:

1. **On page load:** `GET /faces` → render up to 20 tiles oldest-to-newest (so newest ends up at top after prepend)
2. **On WS message `type === "face_capture"`:** prepend tile to panel; if tile count > 20, remove last child
3. **Tile animation:** CSS `slide-in` keyframe (translate Y -10px → 0, opacity 0 → 1, 200ms ease-out)
4. **Counter badge:** incremented on each new tile received

### CSS

Added to `static/css/style.css`. New classes: `.face-captures-panel`, `.face-tile`, `.face-tile-img`, `.face-tile-info`, `.face-tile-male`, `.face-tile-female`, `.face-new-badge`, `.face-unconfirmed`.

---

## Error Handling

- Disk write failure: log error, still broadcast WS message (tile shown without persistent storage)
- `index.json` corruption: rebuild from filenames on startup
- Missing image file (deleted before served): `GET /faces/{filename}` returns 404; frontend shows broken-image placeholder
- WS message while no clients connected: skip broadcast, capture still saved to disk

---

## Out of Scope

- Face search or export
- Configurable retention period (hardcoded 24h)
- Mobile panel layout (panel collapses to stats tab on mobile, same as existing stats)
