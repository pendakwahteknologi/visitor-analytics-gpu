# Visitor Analytics

Real-time CCTV-based visitor counting system with gender and age detection, powered by YOLOv8 and face analysis models.

![Version](https://img.shields.io/badge/version-4.1.0-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-77%20passing-brightgreen)

---

## Features

- **Real-time Person Detection** — YOLOv8n for fast and accurate person detection
- **Gender Classification** — Ensemble approach using InsightFace + DeepFace with weighted majority voting
- **Age Detection** — 5 age groups (Children, Teens, Young Adults, Adults, Seniors) with median aggregation
- **Face Re-identification** — Multi-biometric fusion (face 60% + gender 20% + age 10% + temporal 10%) prevents double-counting
- **Confirmation System** — Visitors must be detected 3 times before counting, eliminating false positives
- **Live Video Stream** — WebSocket-based streaming with JPEG encoding
- **Modern Dashboard** — Dark-themed responsive UI optimized for large displays
- **Login Authentication** — Session-based login with HMAC-signed cookies for browser access
- **API Key Auth** — Header-based API key for programmatic/external access
- **SQLite Storage** — WAL-mode database with automatic JSON migration for historical statistics
- **Embedding Encryption** — Optional Fernet encryption for face embeddings at rest
- **Crash Resilience** — Atomic file writes, signal handlers, and auto-save every 30 seconds
- **Security Hardened** — CSP headers, rate limiting, CORS, XSS protection, RTSP credential sanitization
- **Audit Logging** — Every request logged with IP, method, path, status, duration, and auth method
- **CSV Export** — Download historical statistics as CSV
- **Nginx Reverse Proxy** — Production deployment behind Nginx with gzip, WebSocket upgrade, and static asset caching
- **Server Hardening** — Localhost-only binding, systemd watchdog, UFW firewall, logrotate
- **77 Automated Tests** — Unit, integration, and WebSocket load tests

---

## System Architecture

```
┌─────────────────┐
│   CCTV Camera   │  RTSP Stream
└────────┬────────┘
         │
         v
┌──────────────────────────────────────┐
│           Python Server              │
│  ├─ YOLOv8n (Person Detection)       │
│  ├─ InsightFace + DeepFace (Demographics)
│  ├─ VisitorTracker (Re-identification)
│  ├─ SQLite (Statistics Storage)      │
│  ├─ FastAPI + WebSocket              │
│  └─ Session/API Key Auth             │
└────────┬─────────────────────────────┘
         │
         v
┌──────────────────────────────────────┐
│         Nginx (Port 80)              │
│  ├─ Reverse Proxy → localhost:8000   │
│  ├─ Gzip Compression                │
│  ├─ WebSocket Upgrade               │
│  └─ Static Asset Caching (7d)       │
└────────┬─────────────────────────────┘
         │
         v
┌──────────────────────────────────────┐
│          Web Dashboard               │
│  ├─ Login Page (session cookie)      │
│  ├─ Live Video Feed                  │
│  ├─ Today / Weekly / Monthly / All-time Stats
│  ├─ Gender & Age Distribution        │
│  └─ Settings & Controls              │
└──────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.12, FastAPI, Uvicorn (localhost:8000) |
| ML Models | YOLOv8n, InsightFace (buffalo_l), DeepFace |
| Storage | SQLite (WAL mode), Atomic JSON writes |
| Auth | Session cookies (HMAC-SHA256) + API key |
| Encryption | Fernet (optional, for embeddings at rest) |
| Streaming | WebSocket, JPEG encoding |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Reverse Proxy | Nginx (port 80 → localhost:8000) |
| Testing | pytest, httpx, websockets, pytest-asyncio |

---

## Project Structure

```
visitor-stat/
├── backend/
│   ├── main.py              # FastAPI app, middleware, auth, endpoints
│   ├── config.py            # Configuration from environment
│   ├── cctv_handler.py      # CCTV camera connection (RTSP)
│   ├── detection.py         # YOLOv8 + InsightFace + DeepFace + VisitorTracker
│   ├── streaming.py         # WebSocket video streaming
│   ├── data_storage.py      # SQLite statistics persistence
│   ├── visitor_state.py     # Visitor state persistence + encryption
│   └── atomic_write.py      # Safe file writing utilities
├── frontend/
│   ├── index.html           # Dashboard UI
│   └── login.html           # Login page
├── static/
│   ├── css/style.css        # Dark theme styling
│   └── js/app.js            # Dashboard logic
├── tests/
│   ├── conftest.py          # Shared fixtures
│   ├── test_detection_utils.py   # Age groups, Detection dataclass, face size
│   ├── test_visitor_tracker.py   # Confirmation, re-id, median age, eviction
│   ├── test_data_storage.py      # SQLite CRUD, aggregation, CSV, migration
│   ├── test_atomic_write.py      # Round-trip, corruption recovery
│   ├── test_api.py               # Endpoints, auth, login flow, security headers
│   ├── test_cctv_handler.py      # URL sanitization, reconnection backoff
│   ├── test_visitor_state.py     # Persistence, Fernet encryption
│   └── test_websocket_load.py    # Concurrent WebSocket clients
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies (pinned ~=)
├── run.sh                   # Dev startup script
├── restart-services.sh      # Production restart script
├── TODO.md                  # Completed task tracker
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- RTSP-compatible CCTV camera
- ~2GB RAM available

### Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/pendakwahteknologi/visitor-analytics.git
   cd visitor-analytics
   ```

2. **Create virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your camera credentials and security settings (see [Configuration](#configuration)).

5. **Start the server**

   ```bash
   ./run.sh
   ```

   Or manually:

   ```bash
   cd backend
   uvicorn main:app --host 127.0.0.1 --port 8000
   ```

6. **Open the dashboard**

   Navigate to `http://localhost:8000` (direct) or `http://<server-ip>/` (via Nginx). If `ADMIN_PASSWORD` is set, you'll see the login page.

---

## Configuration

All configuration is done via environment variables in the `.env` file:

### Camera

| Variable | Description | Default |
|----------|-------------|---------|
| `CAMERA_IP` | CCTV camera IP address | *required* |
| `CAMERA_USERNAME` | Camera login username | *required* |
| `CAMERA_PASSWORD` | Camera login password | *required* |
| `CAMERA_RTSP_URL` | Full RTSP URL (overrides above) | — |

### Detection

| Variable | Description | Default |
|----------|-------------|---------|
| `CONFIDENCE_THRESHOLD` | Person detection confidence (0.1–0.95) | `0.5` |
| `GENDER_ENABLED` | Enable gender/age detection | `true` |
| `GENDER_THRESHOLD` | Gender detection confidence | `0.6` |
| `YOLO_MODEL` | YOLO model file | `yolov8n.pt` |

### Streaming

| Variable | Description | Default |
|----------|-------------|---------|
| `STREAM_FPS` | Streaming frame rate | `10` |
| `JPEG_QUALITY` | JPEG compression quality (0–100) | `65` |

### Server

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `DEBUG` | Enable debug logging | `False` |
| `TZ` | Timezone | `UTC` |

### Authentication

| Variable | Description | Default |
|----------|-------------|---------|
| `ADMIN_USERNAME` | Dashboard login username | `admin` |
| `ADMIN_PASSWORD` | Dashboard login password (empty = no login required) | — |
| `SESSION_SECRET` | HMAC signing key for session cookies (auto-generated if empty) | — |
| `SESSION_MAX_AGE` | Session expiry in seconds | `86400` (24h) |
| `API_KEY` | API key for programmatic access (empty = no key required) | — |

### Security

| Variable | Description | Default |
|----------|-------------|---------|
| `CORS_ORIGINS` | Comma-separated allowed origins | — |
| `EMBEDDING_ENCRYPTION_KEY` | Fernet key for face embedding encryption | — |

### Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_FILE` | Log file path | `logs/visitor-stat.log` |
| `LOG_MAX_BYTES` | Max log file size | `10485760` (10 MB) |
| `LOG_BACKUP_COUNT` | Number of rotated log files | `5` |

---

## Authentication

The system supports two authentication modes that can be used independently or together:

### Browser Login (Session-based)

Set `ADMIN_PASSWORD` in `.env` to enable. Users visit `/login`, enter credentials, and receive an HttpOnly session cookie valid for 24 hours (configurable via `SESSION_MAX_AGE`).

```bash
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### API Key (Header-based)

Set `API_KEY` in `.env` for programmatic access. Pass the key via `X-API-Key` header or `?api_key=` query parameter.

```bash
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
```

### Open Access

Leave both `ADMIN_PASSWORD` and `API_KEY` empty for unauthenticated access (development/trusted networks only).

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | Session | Dashboard UI (redirects to `/login` if not authenticated) |
| `/login` | GET | — | Login page |
| `/login` | POST | — | Authenticate (form: username, password) |
| `/logout` | GET | — | Clear session and redirect to login |
| `/health` | GET | — | Health check with model status |
| `/settings` | GET/POST | Yes | Get or update detection settings |
| `/stats` | GET | Yes | Current visitor statistics |
| `/stats/weekly` | GET | Yes | Weekly aggregated statistics |
| `/stats/monthly` | GET | Yes | Monthly aggregated statistics |
| `/stats/all-time` | GET | Yes | All-time aggregated statistics |
| `/stats/export` | GET | Yes | Download CSV of all historical data |
| `/reset-stats` | POST | Yes | Reset today's statistics |
| `/stream/start` | POST | Yes | Start CCTV monitoring |
| `/stream/stop` | POST | Yes | Stop CCTV monitoring |
| `/ws/stream` | WebSocket | Yes | Live video feed |

---

## How It Works

### Visitor Counting Pipeline

1. **Person Detection** — YOLOv8n identifies people in each frame (confidence >= 0.5)
2. **Face Analysis** — InsightFace + DeepFace ensemble extracts gender, age, and 512D face embeddings
3. **Minimum Face Validation** — Faces smaller than 40x40 pixels are rejected
4. **Confirmation** — New faces must be detected 3 times within 30 seconds before counting
5. **Re-identification** — Multi-biometric fusion score prevents double-counting returning visitors
6. **Median Age** — Age is stabilized via median across all sightings of a visitor
7. **Statistics** — Unique counts stored in SQLite (WAL mode), auto-saved every 30 seconds

### Security Layers

| Layer | Protection |
|-------|-----------|
| Authentication | Session cookies + API key |
| Rate Limiting | Token bucket (10 req/s, burst 30) per IP |
| CSP Headers | Content-Security-Policy, X-Frame-Options, X-Content-Type-Options |
| XSS Prevention | All dynamic content uses `textContent`, never `innerHTML` |
| CORS | Configurable allowed origins |
| Log Sanitization | RTSP credentials masked in all log output |
| Audit Trail | Every request logged with IP, method, path, status, duration |
| Encryption | Optional Fernet encryption for face embeddings at rest |

### Performance

| Metric | Value |
|--------|-------|
| Detection FPS | 8–10 |
| Latency | < 500ms |
| Bandwidth | 2–3 Mbps |
| CPU Usage | 40–60% |
| Memory | ~2 GB |
| Max Active Visitors | 500 (oldest evicted) |

---

## Testing

Run the full test suite:

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

**77 tests** across 9 test files:

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_detection_utils.py` | 9 | Age groups, Detection dataclass, MIN_FACE_SIZE |
| `test_visitor_tracker.py` | 12 | Confirmation (1/2/3 detections), re-id, median age, eviction, reset |
| `test_data_storage.py` | 9 | SQLite save/retrieve, overwrite, aggregation, CSV export, JSON migration |
| `test_atomic_write.py` | 6 | Round-trip, corruption recovery, nested data, parent dir creation |
| `test_api.py` | 22 | Health, auth enforcement, settings validation, login flow, security headers |
| `test_cctv_handler.py` | 4 | URL sanitization, exponential backoff |
| `test_visitor_state.py` | 4 | Persistence round-trip, Fernet encryption |
| `test_websocket_load.py` | 5 | 10 concurrent clients, rapid connect/disconnect, staggered connections |

---

## Production Deployment

### Infrastructure

The production server runs on Ubuntu 22.04 with the following stack:

```
Internet → UFW Firewall (22, 80, 443) → Nginx (port 80) → Uvicorn (localhost:8000)
```

| Component | Configuration |
|-----------|--------------|
| **Nginx** | Reverse proxy on port 80, gzip compression, WebSocket upgrade, static asset caching (7d) |
| **Uvicorn** | Bound to `127.0.0.1:8000` (not externally accessible) |
| **Systemd** | `visitor-stat.service` with WatchdogSec=120, auto-restart, LimitNOFILE=65535 |
| **UFW** | Only ports 22 (SSH), 80 (HTTP), 443 (HTTPS) open |
| **Logrotate** | Daily rotation, 14 days retention, 50MB max per file |
| **Cron** | Midnight daily restart via `restart-services.sh` |

### Service Management

```bash
# Check status
sudo systemctl status visitor-stat

# Restart
sudo systemctl restart visitor-stat

# View logs
journalctl -u visitor-stat -f

# Application logs
tail -f logs/visitor-stat.log

# Nginx logs
tail -f /var/log/nginx/access.log
```

---

## Privacy & Compliance

- No video recording — all analysis is done in real-time
- No face images stored — only numerical embeddings for re-identification during the session
- Anonymous statistics only — no personally identifiable information
- Embeddings cleared after 30 minutes of inactivity
- Optional Fernet encryption for embeddings at rest
- Old data auto-deleted after 365 days (configurable)

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Video not showing | Ensure camera is reachable and RTSP URL is correct |
| Low FPS (< 10) | Disable gender detection or check server CPU usage |
| All gender "Unknown" | Ensure people face the camera with good lighting |
| Connection drops | System auto-reconnects with exponential backoff (5s–60s) |
| Can't access dashboard | Check `ADMIN_PASSWORD` is set and credentials are correct |
| 401 on API calls | Provide `X-API-Key` header or authenticate via `/login` |
| Stats lost after restart | Set `SESSION_SECRET` in `.env` for persistent sessions |

---

## License

This project is developed by **Bahagian Transformasi Digital**.

Built with:
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- [InsightFace](https://github.com/deepinsight/insightface)
- [DeepFace](https://github.com/serengil/deepface)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenCV](https://opencv.org/)
