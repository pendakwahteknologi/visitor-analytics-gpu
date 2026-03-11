# Visitor Analytics GPU

Real-time CCTV-based visitor counting system with gender, age, and body Re-ID, fully GPU-accelerated using YOLO + ByteTrack and InsightFace on NVIDIA hardware.

![Version](https://img.shields.io/badge/version-6.0.0-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-green)
![YOLO](https://img.shields.io/badge/YOLO-Ultralytics-purple)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-117%20passing-brightgreen)

---

## What's New in v6.0.0 (ByteTrack Edition)

| Improvement | Detail |
|---|---|
| **ByteTrack** | YOLO built-in tracker replaces frame-to-frame detect(); each person gets a stable `track_id` while in scene |
| **Body Re-ID (OSNet)** | torchreid OSNet extracts 512-dim body embeddings for cross-session re-identification (same person returns → not re-counted) |
| **BodyReIDTracker** | Replaces old VisitorTracker; confirmation-based counting (3× detections) eliminates false positives |
| **Body Gender Fallback** | HuggingFace `rizvandwiki/gender-classification-2` classifies gender from body crop when face is not visible |
| **Min-Size Filter** | Detections smaller than 50×100 px are dropped — eliminates ghost/background false positives |
| **No Count Inflation** | Fixed root cause of inflated counts (21×36 px bbox → `_count_only()` every frame) |
| **Face Captures Panel** | Live tiles showing face snapshots with gender label as visitors are detected |
| **Person Captures Panel** | Live tiles showing body snapshots at the moment each visitor is confirmed |
| **PDF Report Redesign** | "Unique Persons" terminology, KPI cards, daily breakdown tables, section dividers |
| **State Encryption** | Optional Fernet AES encryption for body embeddings at rest (`EMBEDDING_ENCRYPTION_KEY`) |

---

## Features

- **Real-time Person Detection** — YOLO + ByteTrack at imgsz=1280 with FP16 on GPU
- **ByteTrack Tracking** — Stable track IDs per person, called every frame for reliable state
- **Body Re-identification** — OSNet 512-dim embeddings, cosine similarity across sessions
- **Unique Visitor Counting** — Confirmation-based (3× detections required before counting)
- **Gender & Age Classification** — InsightFace (buffalo_l) + DeepFace ensemble; body-based fallback
- **Face & Person Capture Panels** — Live dashboard tiles with real-time WebSocket updates
- **Live Video Stream** — WebSocket-based streaming, JPEG quality configurable
- **Modern Dashboard** — Dark-themed responsive UI, today/weekly/monthly/all-time stats
- **HTTPS** — mkcert SSL, HTTP→HTTPS redirect, works on any DHCP network
- **mDNS** — `visitor-analysis.local` resolves automatically on LAN (no DNS config needed)
- **Login Authentication** — Session-based login with HMAC-signed cookies
- **API Key Auth** — Header-based API key for programmatic access
- **SQLite Storage** — WAL-mode database with automatic JSON migration
- **PDF & CSV Reports** — Downloadable reports with historical statistics and unique person counts
- **Crash Resilience** — Atomic file writes, signal handlers, auto-save every 30 seconds
- **Security Hardened** — CSP headers, rate limiting, timing-attack-safe comparisons, thread-safe ID generation
- **Audit Logging** — Every request logged with IP, method, path, status, duration, and auth method

---

## System Architecture

```
┌─────────────────┐
│   CCTV Camera   │  RTSP Stream
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│           Python / FastAPI Server            │
│  ├─ YOLO (PersonDetector.track, ByteTrack)   │
│  ├─ Min-size filter (W<50 or H<100 → drop)  │
│  ├─ OSNet Re-ID (body embeddings 512-dim)    │
│  ├─ InsightFace buffalo_l (face gender/age)  │
│  ├─ BodyGenderAnalyzer (HuggingFace, CPU)    │
│  ├─ BodyReIDTracker (confirmation + Re-ID)   │
│  ├─ SQLite WAL (Statistics)                  │
│  ├─ WebSocket Streaming                      │
│  └─ HTTPS (mkcert, port 443)                 │
└────────┬─────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│   mDNS (Avahi) — visitor-analysis.local      │
│   HTTP :80 → HTTPS :443 redirect             │
└────────┬─────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│          Web Dashboard                       │
│  ├─ https://visitor-analysis.local/          │
│  ├─ Live Video Feed                          │
│  ├─ Today / Weekly / Monthly / All-time      │
│  ├─ Gender & Age Distribution                │
│  ├─ Face Captures Panel (live tiles)         │
│  ├─ Person Captures Panel (live tiles)       │
│  └─ PDF / CSV Export                         │
└──────────────────────────────────────────────┘
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
| Body Re-ID | torchreid OSNet (512-dim embeddings) |
| Face Analysis | InsightFace buffalo_l (CUDA), DeepFace |
| Body Gender | HuggingFace transformers (`rizvandwiki/gender-classification-2`) |
| ONNX Runtime | onnxruntime-gpu (CUDAExecutionProvider) |
| Storage | SQLite (WAL mode), Atomic JSON writes |
| Auth | Session cookies (HMAC-SHA256) + API key |
| Streaming | WebSocket, JPEG encoding |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| HTTPS | mkcert (locally trusted CA) |
| mDNS | Avahi daemon (`visitor-analysis.local`) |
| Testing | pytest, httpx, websockets, pytest-asyncio (117 tests) |

---

## Project Structure

```
visitor-analytics/
├── backend/
│   ├── main.py              # FastAPI app, middleware, auth, endpoints
│   ├── config.py            # Configuration from environment
│   ├── cctv_handler.py      # CCTV camera connection (RTSP)
│   ├── detection.py         # YOLO, PersonDetector.track(), OSNet, InsightFace,
│   │                        # BodyGenderAnalyzer, BodyReIDTracker, DetectionEngine
│   ├── streaming.py         # WebSocket video streaming (ByteTrack loop)
│   ├── data_storage.py      # SQLite statistics persistence
│   ├── pdf_report.py        # PDF report generation (ReportLab)
│   ├── visitor_state.py     # Visitor state persistence + encryption
│   └── atomic_write.py      # Safe file writing utilities
├── frontend/
│   ├── index.html           # Dashboard UI (face + person capture panels)
│   └── login.html           # Login page
├── static/
│   ├── css/style.css        # Dark theme styling
│   └── js/app.js            # Dashboard logic, WebSocket, capture tiles
├── certs/                   # SSL certificates (mkcert, not committed)
├── tests/                   # 117 automated tests
├── docs/
│   └── superpowers/         # Design specs and implementation plans
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
└── run.sh                   # Dev startup script
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
CONFIDENCE_THRESHOLD=0.5
STREAM_FPS=15
JPEG_QUALITY=80
TZ=Asia/Kuala_Lumpur
```

### 4. SSL Certificate (for HTTPS)

```bash
# Install mkcert
wget -q https://dl.filippo.io/mkcert/latest?for=linux/amd64 -O mkcert
sudo install mkcert /usr/local/bin/mkcert

# Generate certificate
mkdir certs
mkcert -cert-file certs/cert.pem -key-file certs/key.pem visitor-analysis.local localhost 127.0.0.1
```

### 5. mDNS (hostname resolution)

```bash
sudo apt install avahi-daemon
sudo systemctl enable --now avahi-daemon
```

### 6. Run

```bash
# HTTPS on port 443
uvicorn backend/main:app --host 0.0.0.0 --port 443 \
  --ssl-certfile certs/cert.pem --ssl-keyfile certs/key.pem
```

Or use the systemd service (see [Production Deployment](#production-deployment)).

### 7. Trust the CA Certificate on Client Machines

Download from: `https://visitor-analysis.local/rootCA.pem`

**macOS:** Double-click → Keychain Access → set **Always Trust**

**Windows:** Double-click → Install Certificate → Local Machine → Trusted Root Certification Authorities

---

## Accessing the Dashboard

| URL | Description |
|---|---|
| `https://visitor-analysis.local` | Main dashboard |
| `https://visitor-analysis.local/rootCA.pem` | Download CA certificate |
| `http://visitor-analysis.local` | Auto-redirects to HTTPS |

Works on any DHCP network — `visitor-analysis.local` resolves via mDNS regardless of IP.

---

## Configuration

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
| `CONFIDENCE_THRESHOLD` | Person detection confidence (0.1–0.95) | `0.5` |
| `GENDER_ENABLED` | Enable gender/age detection | `true` |
| `YOLO_MODEL` | YOLO model file | `yolov8n.pt` |
| `MIN_PERSON_W` | Minimum detection width in pixels | `50` |
| `MIN_PERSON_H` | Minimum detection height in pixels | `100` |
| `BODY_GENDER_CONFIDENCE` | Body gender classifier min confidence | `0.70` |

### Streaming

| Variable | Description | Default |
|---|---|---|
| `STREAM_FPS` | Streaming frame rate | `15` |
| `JPEG_QUALITY` | JPEG quality (0–100) | `80` |

### Server

| Variable | Description | Default |
|---|---|---|
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | Server port | `443` |
| `TZ` | Timezone | `Asia/Kuala_Lumpur` |

### Authentication

| Variable | Description | Default |
|---|---|---|
| `ADMIN_USERNAME` | Dashboard username | `admin` |
| `ADMIN_PASSWORD` | Dashboard password (empty = no auth) | — |
| `SESSION_SECRET` | HMAC signing key (auto-generated if empty) | — |
| `SESSION_MAX_AGE` | Session expiry in seconds | `86400` |
| `API_KEY` | API key for programmatic access | — |

### Security (Optional)

| Variable | Description | Default |
|---|---|---|
| `EMBEDDING_ENCRYPTION_KEY` | Fernet key for embedding encryption at rest | — |

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | Session | Dashboard UI |
| `/login` | GET/POST | — | Login page / authenticate |
| `/logout` | GET | — | Clear session |
| `/health` | GET | — | Health check |
| `/settings` | GET/POST | Yes | Detection settings |
| `/stats` | GET | Yes | Current statistics |
| `/stats/weekly` | GET | Yes | Weekly statistics |
| `/stats/monthly` | GET | Yes | Monthly statistics |
| `/stats/all-time` | GET | Yes | All-time statistics |
| `/stats/export` | GET | Yes | CSV export |
| `/stats/export/pdf` | GET | Yes | PDF report |
| `/reset-stats` | POST | Yes | Reset today's stats |
| `/capture/faces` | GET | Yes | Recent face captures |
| `/capture/persons` | GET | Yes | Recent person captures |
| `/ws/stream` | WebSocket | Yes | Live video feed |
| `/rootCA.pem` | GET | — | Download CA certificate |

---

## Security

| Layer | Implementation |
|---|---|
| HTTPS | mkcert locally-trusted certificate |
| Authentication | HMAC-SHA256 session cookies + API key |
| Timing Attacks | `hmac.compare_digest()` for all credential comparisons |
| Rate Limiting | Thread-safe token bucket (10 req/s, burst 30) per IP |
| Thread Safety | Locks on visitor ID generation and rate limiter |
| Async Safety | `return_exceptions=True` on all `asyncio.gather()` calls |
| CSP Headers | Content-Security-Policy, X-Frame-Options, X-Content-Type-Options |
| Private Network | `Access-Control-Allow-Private-Network: true` header |
| CORS | Configurable allowed origins |
| Embedding Encryption | Optional Fernet AES for body embeddings at rest |
| Audit Trail | Every request logged with IP, method, path, status, duration |

---

## Performance (NVIDIA RTX A2000)

| Metric | Value |
|---|---|
| Stream FPS | 15 |
| ByteTrack | Every frame (required for consistent track state) |
| OSNet + Face analysis | Every 4th frame (heavy computation) |
| GPU VRAM | ~1.4 GB |
| GPU Utilisation | 20–60% |
| Latency | < 200ms |

---

## Production Deployment

### systemd Services

```bash
# Main app
sudo systemctl status visitor-analytics

# HTTP → HTTPS redirect
sudo systemctl status http-redirect

# mDNS
sudo systemctl status avahi-daemon

# Restart all
sudo systemctl restart visitor-analytics http-redirect
```

### Firewall (UFW)

```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### Logs

```bash
# Live application logs
journalctl -u visitor-analytics -f

# Application log file
tail -f logs/visitor-stat.log
```

---

## Troubleshooting

| Issue | Solution |
|---|---|
| Chrome/Edge can't connect (macOS) | System Settings → Privacy & Security → Local Network → enable browser |
| Certificate not trusted | Download `https://visitor-analysis.local/rootCA.pem` and install as trusted CA |
| `visitor-analysis.local` not resolving | Ensure Avahi is running: `sudo systemctl start avahi-daemon` |
| Camera not connecting | Check RTSP URL and ensure camera is on the same network |
| GPU not used | Verify `nvidia-smi` shows the process; ensure `onnxruntime-gpu` is installed |
| All gender "Unknown" | Ensure people face camera with adequate lighting, or enable body-gender fallback |
| Visitor count inflated | Check `MIN_PERSON_W`/`MIN_PERSON_H` in `.env`; increase if small false positives appear |
| Stats lost after restart | Set `SESSION_SECRET` in `.env` |
| Body gender model slow first run | First call downloads `rizvandwiki/gender-classification-2` (~14 MB); subsequent calls are instant |

---

## Privacy & Compliance

- No video recording — all analysis is real-time only
- No face images stored permanently — capture tiles are session-only
- Anonymous statistics only — no personally identifiable information
- Body embeddings cleared after 30 minutes of inactivity
- Optional Fernet encryption for embeddings at rest
- Old data auto-deleted after 365 days (configurable)

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
- [mkcert](https://github.com/FiloSottile/mkcert)
