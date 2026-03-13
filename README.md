# Visitor Analytics GPU

Real-time CCTV-based visitor counting system with gender, age, and body Re-ID, fully GPU-accelerated using YOLO + ByteTrack and InsightFace on NVIDIA hardware.

![Version](https://img.shields.io/badge/version-6.2.0-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-green)
![YOLO](https://img.shields.io/badge/YOLO-Ultralytics-purple)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-152%20passing-brightgreen)

---

## What's New in v6.2.0

| Improvement | Detail |
|---|---|
| **Unique Visitor Counter** | Counter increments when a unique person is confirmed by Re-ID — gender/age are secondary and never block counting |
| **Track-Only Re-ID** | Persons too small/far for OSNet embedding are now tracked by `track_id` and counted after 3 confirmed sightings — no one is silently skipped |
| **Real-Time Counter** | Dashboard uses live in-memory session count (no 30s lag); today's DB value acts as a floor after restarts |
| **Immediate DB Save** | Visitor count is flushed to the database the moment a new unique person is confirmed, not on a 30s timer |
| **Event Loop Fix** | `BodyGenderAnalyzer.predict()` (HuggingFace CPU inference) moved to thread executor — eliminates dashboard hang under load |
| **Offline Model Cache** | HuggingFace gender model pre-downloaded to `models/huggingface/`; `HF_HUB_OFFLINE=1` prevents any internet access at runtime |

---

## What's New in v6.1.0

| Improvement | Detail |
|---|---|
| **Production Hardening** | `asyncio.get_running_loop()` for safe executor dispatch, `model_lock` for serialised YOLO inference |
| **Non-blocking Tracking** | `person_detector.track()` runs in executor to unblock the async event loop |
| **Auto-restart Stream** | Stream loop auto-restarts on transient errors instead of dying silently |
| **ByteTrack** | YOLO built-in tracker replaces frame-to-frame detect(); each person gets a stable `track_id` while in scene |
| **Body Re-ID (OSNet)** | torchreid OSNet extracts 512-dim body embeddings for cross-session re-identification |
| **BodyReIDTracker** | Confirmation-based counting (3× detections) eliminates false positives |
| **Body Gender Fallback** | HuggingFace `rizvandwiki/gender-classification-2` classifies gender from body crop when face is not visible |
| **Face & Person Captures** | Live tiles showing face/body snapshots with gender label as visitors are detected |

---

## How Visitor Counting Works

Understanding the two counters on the dashboard is important.

### Current Count vs Total Visitors

| Counter | What it measures | When it updates |
|---|---|---|
| **Current Count** | Number of people YOLO detects in the camera frame right now | Every frame, real-time |
| **Total Visitors** | Number of unique individuals confirmed by Re-ID this session | When each new person is confirmed (~1–2 seconds after first appearing) |

These two numbers are **intentionally different**. A person appearing in the frame does not immediately become a counted visitor — they go through a confirmation process first.

### The Confirmation Process

When a person enters the camera's field of view:

```
Person enters frame
       │
       ▼
YOLO detects them (instant)
Current Count increases immediately
       │
       ▼
Size filter: width ≥ 50px AND height ≥ 100px?
       │ No → dropped (too small/far to be a real person)
       │ Yes ↓
       ▼
OSNet extracts body embedding from crop
       │
       ├─ Embedding OK → matched against known persons
       │                  (cosine similarity ≥ 0.60 = known person, not re-counted)
       │                  New person? → accumulate 3 confirmations → count
       │
       └─ Crop too small for OSNet → Track-Only Re-ID path
                  │
                  ▼
         Accumulate seen_count by track_id
                  │
       ┌──────────┴──────────┐
       │ seen_count < 3       │ seen_count ≥ 3
       │ (still pending)      │ (confirmed!)
       ▼                      ▼
  Not yet counted        Total Visitors + 1
                         DB saved immediately
                         If person later walks closer →
                         upgraded with real embedding,
                         no double-count
```

**Why require 3 confirmations?**
Without it, anyone briefly walking past the edge of frame, a YOLO false positive, or a partial view of the same person would inflate the count. Three consecutive analysis frames (run every 4th video frame) ensures the person is genuinely present — at ~8 FPS this takes about 1–2 seconds.

### What This Means in Practice

- You may see **Current Count = 2** but **Total Visitors = 1** — this is correct and expected. The second person was detected but hasn't completed their 3-frame confirmation yet. Within 1–2 seconds of remaining visible, Total Visitors will increment to 2.
- A person who **leaves and returns** will be re-identified by their body embedding and **not re-counted**.
- A person who is **far from the camera** (small crop) is tracked by `track_id` via the Track-Only Re-ID path and still counted once confirmed — they are never silently dropped.
- **Gender and age are secondary** — a person is counted as a unique visitor regardless of whether gender or age could be determined. Unknown gender is recorded, but it never blocks the count.

### Gender & Age Detection Pipeline

Gender and age are enriched after confirmation, not as a prerequisite for it:

1. **InsightFace** (primary) — detects face, estimates gender + age from face crop
2. **DeepFace** (secondary) — ensemble with InsightFace for higher accuracy
3. **Body Gender fallback** — when no face is visible, `rizvandwiki/gender-classification-2` classifies gender from the full body crop (CPU, HuggingFace Transformers, runs offline)

If none of the above can classify gender, the person is counted as **Unknown** — they are still counted as a unique visitor.

---

## Features

- **Real-time Person Detection** — YOLO + ByteTrack at imgsz=1280 with FP16 on GPU
- **ByteTrack Tracking** — Stable track IDs per person, called every frame for reliable state
- **Body Re-identification** — OSNet 512-dim embeddings (CPU), cosine similarity across sessions
- **Unique Visitor Counting** — Confirmation-based (3 sightings required); gender never blocks a count
- **Track-Only Re-ID** — Persons too small for OSNet are counted via track_id — no silent drops
- **Real-Time Counter** — Live session count, flushed to DB immediately on each new unique person
- **Gender & Age Classification** — InsightFace (buffalo_l) + DeepFace ensemble; body-based fallback
- **Offline AI Models** — HuggingFace model cached locally; no internet required at runtime
- **Face & Person Capture Panels** — Live dashboard tiles with real-time WebSocket updates
- **Live Video Stream** — WebSocket-based MJPEG streaming, JPEG quality configurable
- **Modern Dashboard** — Dark-themed responsive UI, today/weekly/monthly/all-time stats
- **Login Authentication** — Session-based login with HMAC-signed cookies
- **API Key Auth** — Header-based API key for programmatic access
- **SQLite Storage** — WAL-mode database with automatic JSON migration
- **PDF & CSV Reports** — Downloadable reports with historical statistics and unique person counts
- **Crash Resilience** — Atomic file writes, signal handlers, immediate save on new visitor, auto-restart stream loop
- **Security Hardened** — CSP headers, rate limiting, timing-attack-safe comparisons, thread-safe ID generation
- **Audit Logging** — Every request logged with IP, method, path, status, duration, and auth method

---

## System Architecture

```
┌─────────────────┐
│   CCTV Camera   │  RTSP Stream (TCP)
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│               Python / FastAPI Server                │
│                                                      │
│  Every frame:                                        │
│  ├─ YOLO (PersonDetector.track, ByteTrack)           │
│  └─ Min-size filter (W<50px or H<100px → drop)       │
│                                                      │
│  Every 4th frame (analysis):                         │
│  ├─ OSNet Re-ID (body embeddings, CPU)               │
│  │   └─ Too small → Track-Only Re-ID (by track_id)  │
│  ├─ InsightFace buffalo_l (face gender/age, GPU)     │
│  ├─ DeepFace ensemble (face gender/age)              │
│  ├─ BodyGenderAnalyzer (HuggingFace, CPU, executor)  │
│  └─ BodyReIDTracker (3× confirm → count unique)      │
│                                                      │
│  On new unique person confirmed:                     │
│  └─ Immediate SQLite save + WebSocket broadcast      │
│                                                      │
│  Infrastructure:                                     │
│  ├─ SQLite WAL (statistics)                          │
│  ├─ WebSocket streaming                              │
│  └─ HTTP on port 80                                  │
└────────┬─────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────┐
│              Web Dashboard                           │
│  ├─ http://<server-ip>/                              │
│  ├─ Live Video Feed                                  │
│  ├─ Current Count (real-time YOLO detections)        │
│  ├─ Total Visitors (unique Re-ID confirmed, live)    │
│  ├─ Today / Weekly / Monthly / All-time stats        │
│  ├─ Gender & Age Distribution                        │
│  ├─ Face Captures Panel (live tiles)                 │
│  ├─ Person Captures Panel (live tiles)               │
│  └─ PDF / CSV Export                                 │
└──────────────────────────────────────────────────────┘
```

---

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA GTX 1060 6GB | NVIDIA RTX A2000 or better |
| CUDA | 11.8+ | 12.x |
| RAM | 8 GB | 16 GB |
| CPU | 4 cores | 8 cores |
| Python | 3.10+ | 3.12 |

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Object Detection | Ultralytics YOLO + ByteTrack, FP16, GPU |
| Body Re-ID | torchreid OSNet (512-dim embeddings, CPU) |
| Face Analysis | InsightFace buffalo_l (CUDA), DeepFace |
| Body Gender | HuggingFace Transformers (`rizvandwiki/gender-classification-2`, CPU, offline) |
| ONNX Runtime | onnxruntime-gpu (CUDAExecutionProvider) |
| Storage | SQLite (WAL mode), Atomic JSON writes |
| Auth | Session cookies (HMAC-SHA256) + API key |
| Streaming | WebSocket, JPEG encoding |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Testing | pytest, httpx, websockets, pytest-asyncio (152 tests) |

---

## Project Structure

```
visitor-analytics/
├── backend/
│   ├── main.py                # FastAPI app, middleware, auth, endpoints
│   ├── config.py              # Configuration from environment
│   ├── cctv_handler.py        # CCTV camera connection (RTSP, auto-reconnect)
│   ├── detection.py           # YOLO, PersonDetector.track(), OSNet, InsightFace,
│   │                          # BodyGenderAnalyzer, BodyReIDTracker, DetectionEngine
│   ├── streaming.py           # WebSocket video streaming + detection loop
│   ├── data_storage.py        # SQLite statistics persistence
│   ├── pdf_report.py          # PDF report generation (ReportLab)
│   ├── visitor_state.py       # Visitor state persistence + encryption
│   ├── person_capture_store.py # Body crop JPEG storage + index
│   ├── face_capture_store.py  # Face crop JPEG storage + index
│   └── atomic_write.py        # Safe file writing utilities
├── frontend/
│   ├── index.html             # Dashboard UI
│   ├── login.html             # Login page
│   └── detect-all.html        # YOLO all-classes explorer
├── static/
│   ├── css/style.css          # Dark theme styling
│   └── js/
│       ├── app.js             # Dashboard logic, WebSocket, capture tiles
│       └── detect-all.js      # Detect-all page logic
├── models/
│   └── huggingface/           # Pre-cached HuggingFace models (offline)
├── systemd/
│   └── visitor-analytics.service  # systemd unit file
├── tests/                     # 152 automated tests (14 test files)
├── .env.example               # Environment variable template
├── requirements.txt           # Python dependencies
└── run.sh                     # Dev startup script
```

---

## Installation

### 1. Prerequisites

```bash
# Ubuntu 22.04+ with NVIDIA GPU
python3 --version   # 3.10+
nvidia-smi          # CUDA driver installed
```

### 2. Clone & Setup

```bash
git clone https://github.com/pendakwahteknologi/visitor-analytics-gpu.git
cd visitor-analytics-gpu
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
nano .env
```

Key settings:

```env
CAMERA_RTSP_URL=rtsp://user:pass@10.0.0.1:554/Streaming/Channels/101
YOLO_MODEL=yolov8x.pt
CONFIDENCE_THRESHOLD=0.4
STREAM_FPS=25
JPEG_QUALITY=90
TZ=Asia/Kuala_Lumpur
```

### 4. Pre-download HuggingFace Model

The body gender classifier must be downloaded once. After that it runs fully offline.

```bash
HF_HOME=./models/huggingface venv/bin/python3 -c "
from transformers import pipeline
pipeline('image-classification', model='rizvandwiki/gender-classification-2', device=-1)
print('Model cached.')
"
```

Add to `.env`:
```env
HF_HOME=/absolute/path/to/visitor-analytics/models/huggingface
HF_HUB_OFFLINE=1
```

### 5. Run

```bash
# Development
uvicorn backend.main:app --host 0.0.0.0 --port 80
```

---

## Accessing the Dashboard

| URL | Description |
|---|---|
| `http://<server-ip>/` | Main dashboard |
| `http://<server-ip>/detect-all` | YOLO all-classes explorer (all 80 COCO classes) |
| `http://<server-ip>/health` | Health check (no auth required) |

---

## Configuration Reference

### Camera

| Variable | Description | Default |
|---|---|---|
| `CAMERA_IP` | Camera IP address | *required* |
| `CAMERA_USERNAME` | Camera username | *required* |
| `CAMERA_PASSWORD` | Camera password | *required* |
| `CAMERA_RTSP_URL` | Full RTSP URL (overrides above) | — |

### Detection

| Variable | Description | Default |
|---|---|---|
| `CONFIDENCE_THRESHOLD` | Person detection confidence (0.1–0.95) | `0.4` |
| `GENDER_ENABLED` | Enable gender/age detection | `true` |
| `GENDER_THRESHOLD` | InsightFace gender confidence | `0.6` |
| `YOLO_MODEL` | YOLO model file | `yolov8n.pt` |
| `MIN_PERSON_W` | Minimum detection width in pixels | `50` |
| `MIN_PERSON_H` | Minimum detection height in pixels | `100` |
| `BODY_GENDER_CONFIDENCE` | Body gender classifier min confidence | `0.70` |

### Streaming

| Variable | Description | Default |
|---|---|---|
| `STREAM_FPS` | Streaming frame rate | `25` |
| `JPEG_QUALITY` | JPEG quality (0–100) | `90` |

### Server

| Variable | Description | Default |
|---|---|---|
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | Server port | `80` |
| `TZ` | Timezone | `Asia/Kuala_Lumpur` |

### Authentication

| Variable | Description | Default |
|---|---|---|
| `ADMIN_USERNAME` | Dashboard username | `admin` |
| `ADMIN_PASSWORD` | Dashboard password (empty = no auth) | — |
| `SESSION_SECRET` | HMAC signing key (auto-generated if empty) | — |
| `SESSION_MAX_AGE` | Session expiry in seconds | `86400` |
| `API_KEY` | API key for programmatic access | — |

### HuggingFace (Offline Models)

| Variable | Description | Default |
|---|---|---|
| `HF_HOME` | Path to pre-cached HuggingFace models | — |
| `HF_HUB_OFFLINE` | Set to `1` to disable all internet access | — |

### Logging

| Variable | Description | Default |
|---|---|---|
| `LOG_FILE` | Application log file path | `logs/visitor-stat.log` |
| `LOG_MAX_BYTES` | Max log file size before rotation | `10485760` (10 MB) |
| `LOG_BACKUP_COUNT` | Number of rotated log files to keep | `5` |

### Security (Optional)

| Variable | Description | Default |
|---|---|---|
| `EMBEDDING_ENCRYPTION_KEY` | Fernet key for embedding encryption at rest | — |
| `CORS_ORIGINS` | Comma-separated allowed CORS origins | — |

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | Session | Dashboard UI |
| `/login` | GET/POST | — | Login page / authenticate |
| `/logout` | GET | — | Clear session |
| `/health` | GET | — | Health check (model status, uptime) |
| `/settings` | GET/POST | Yes | Detection settings |
| `/stats` | GET | Yes | Live stats (session + today's DB) |
| `/stats/weekly` | GET | Yes | Weekly statistics |
| `/stats/monthly` | GET | Yes | Monthly statistics |
| `/stats/all-time` | GET | Yes | All-time statistics |
| `/stats/export` | GET | Yes | CSV export |
| `/stats/export/pdf` | GET | Yes | PDF report |
| `/reset-stats` | POST | Yes | Reset today's stats |
| `/stream/start` | POST | Yes | Start CCTV capture and detection |
| `/stream/stop` | POST | Yes | Stop CCTV capture |
| `/faces` | GET | Yes | Recent face captures |
| `/faces/{filename}` | GET | Yes | Retrieve face image |
| `/persons` | GET | Yes | Recent person captures |
| `/persons/{filename}` | GET | Yes | Retrieve person image |
| `/detect-all` | GET | — | YOLO all-classes explorer |
| `/ws/stream` | WebSocket | Yes | Live video feed |
| `/ws/detect-all` | WebSocket | — | YOLO all-classes stream |

### `/stats` Response Structure

```json
{
  "current": {
    "total_people": 2,
    "fps": 8
  },
  "session": {
    "total_detected": 1,
    "male_detected": 1,
    "female_detected": 0,
    "age_groups": { ... }
  },
  "today_saved": {
    "total_visitors": 1,
    "male": 1,
    "female": 0,
    "unknown": 0,
    "age_groups": { ... }
  },
  "active_visitors": 1,
  "connections": 4,
  "uptime_seconds": 213
}
```

`current.total_people` — people YOLO sees right now (Current Count on dashboard).
`session.total_detected` — unique persons confirmed this session (Total Visitors, primary).
`today_saved.total_visitors` — persisted DB value, used as floor after a service restart.

---

## Security

| Layer | Implementation |
|---|---|
| Authentication | HMAC-SHA256 session cookies + API key |
| Timing Attacks | `hmac.compare_digest()` for all credential comparisons |
| Rate Limiting | Thread-safe token bucket (10 req/s, burst 30) per IP |
| Thread Safety | Locks on tracker state, visitor ID generation, and rate limiter |
| Async Safety | All CPU-bound inference runs in thread executor; `return_exceptions=True` on all gathers |
| CSP Headers | Content-Security-Policy, X-Frame-Options, X-Content-Type-Options |
| Private Network | `Access-Control-Allow-Private-Network: true` header |
| CORS | Configurable allowed origins |
| Embedding Encryption | Optional Fernet AES for body embeddings at rest |
| Offline AI | HuggingFace model cache locked offline (`HF_HUB_OFFLINE=1`) |
| Audit Trail | Every request logged with IP, method, path, status, duration |

---

## Performance (NVIDIA RTX A2000)

| Metric | Value |
|---|---|
| Stream FPS | ~8–15 (load-dependent) |
| ByteTrack | Every frame |
| OSNet + Face analysis | Every 4th frame |
| New visitor confirmation latency | ~1–2 seconds |
| GPU VRAM | ~1.4 GB |
| GPU Utilisation | 20–60% |

---

## Production Deployment

### systemd Service

```bash
sudo cp systemd/visitor-analytics.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now visitor-analytics

# Status and logs
sudo systemctl status visitor-analytics
journalctl -u visitor-analytics -f
```

The service runs as `root` on port 80 with:
- 180s startup timeout (YOLO + InsightFace model loading)
- Auto-restart on failure (10s delay, max 5 per 5 min)
- Environment loaded from `.env`
- GPU library paths set for CUDA/cuBLAS

### Firewall (UFW)

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP dashboard
sudo ufw enable
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Dashboard hangs / no response | `journalctl -u visitor-analytics -n 50` — confirm service running on port 80 |
| Camera not connecting | Check RTSP URL; confirm camera reachable: `ping <camera-ip>` |
| GPU not used | Verify `nvidia-smi` shows the process; ensure `onnxruntime-gpu` is installed |
| All gender "Unknown" | Ensure people face camera with adequate lighting; body-gender fallback activates automatically |
| **Current Count = 2 but Total Visitors = 1** | **Expected behaviour** — the second person is in the 3-frame confirmation window (~1–2 seconds). Total Visitors will catch up once they're confirmed. |
| Visitor count not incrementing | Check `session.total_detected` in `/stats`; if changing, try `POST /reset-stats` to re-sync with DB |
| Stats lost after restart | State auto-saves on every new unique visitor and on shutdown; check `backend/data/visitor_state.json` |
| Body gender model downloading on startup | Run the pre-download step in Installation and set `HF_HOME` + `HF_HUB_OFFLINE=1` in `.env` |
| Stream dies silently | Stream loop auto-restarts; check logs for crash reason |
| High memory usage | Normal — OSNet on CPU + YOLO/InsightFace on GPU uses ~5 GB RAM for the full stack |

---

## Privacy & Compliance

- No video recording — all analysis is real-time only
- No face images stored permanently — capture tiles cleared daily at midnight
- Anonymous statistics only — no personally identifiable information retained
- Body embeddings cleared after 30 minutes of inactivity
- Optional Fernet encryption for embeddings at rest
- Old capture files auto-deleted after 24 hours

---

## License

Developed by **Bahagian Transformasi Digital**.

Built with:
- [Ultralytics YOLO + ByteTrack](https://docs.ultralytics.com/)
- [torchreid (OSNet)](https://github.com/KaiyangZhou/deep-person-reid)
- [InsightFace](https://github.com/deepinsight/insightface)
- [HuggingFace Transformers](https://huggingface.co/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenCV](https://opencv.org/)
