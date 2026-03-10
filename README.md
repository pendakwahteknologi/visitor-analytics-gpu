# Visitor Analytics GPU

Real-time CCTV-based visitor counting system with gender and age detection, fully GPU-accelerated using YOLO26 and InsightFace on NVIDIA hardware.

![Version](https://img.shields.io/badge/version-5.0.0-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![GPU](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-green)
![YOLO](https://img.shields.io/badge/YOLO-YOLO26x-purple)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-84%20passing-brightgreen)

---

## What's New in v5.0.0 (GPU Edition)

| Improvement | Detail |
|---|---|
| **YOLO26x** | Upgraded from YOLOv8n → YOLO26x (latest Ultralytics model, NMS-free inference) |
| **Full GPU Acceleration** | YOLO26 + InsightFace + ONNX Runtime all running on CUDA |
| **FP16 Inference** | Half-precision for 2× faster GPU throughput |
| **Higher Resolution** | Detection at imgsz=1280 (was 640) — detects people far from camera |
| **InsightFace 1024px** | Face det_size upgraded from 640×640 → 1024×1024 |
| **Parallel Face Analysis** | All faces in a frame analysed concurrently via async thread pool |
| **HTTPS by Default** | mkcert SSL certificate, HTTP auto-redirects to HTTPS |
| **mDNS Hostname** | Access via `https://visitor-analysis.local` regardless of DHCP IP |
| **YOLO26 Explorer Page** | New `/detect-all` page showing all 80 COCO classes live |
| **Security Fixes** | Timing attack fixes, thread safety, async error handling |

---

## Features

- **Real-time Person Detection** — YOLO26x at imgsz=1280 with FP16 on GPU
- **Gender & Age Classification** — InsightFace (buffalo_l) + DeepFace ensemble with GPU acceleration
- **Face Re-identification** — Multi-biometric fusion (face 60% + gender 20% + age 10% + temporal 10%) prevents double-counting
- **Confirmation System** — Visitors must be detected 3× before counting, eliminating false positives
- **Live Video Stream** — WebSocket-based streaming at 25 FPS, JPEG quality 90%
- **YOLO26 Explorer** — Dedicated page showing all 80 detectable COCO classes on the live feed
- **Modern Dashboard** — Dark-themed responsive UI for large displays
- **HTTPS** — mkcert SSL, HTTP→HTTPS redirect, works on any DHCP network
- **mDNS** — `visitor-analysis.local` resolves automatically on LAN (no DNS config needed)
- **Login Authentication** — Session-based login with HMAC-signed cookies
- **API Key Auth** — Header-based API key for programmatic access
- **SQLite Storage** — WAL-mode database with automatic JSON migration
- **PDF & CSV Reports** — Downloadable reports with historical statistics
- **Crash Resilience** — Atomic file writes, signal handlers, auto-save every 30 seconds
- **Security Hardened** — CSP headers, rate limiting, timing-attack-safe comparisons, thread-safe ID generation
- **Audit Logging** — Every request logged with IP, method, path, status, duration, and auth method

---

## System Architecture

```
┌─────────────────┐
│   CCTV Camera   │  RTSP Stream (main stream, Channel 101)
└────────┬────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│           Python / FastAPI Server        │
│  ├─ YOLO26x (Person Detection, GPU FP16) │
│  ├─ InsightFace buffalo_l (GPU CUDA)     │
│  ├─ DeepFace (Gender/Age ensemble)       │
│  ├─ VisitorTracker (Re-identification)   │
│  ├─ SQLite WAL (Statistics)              │
│  ├─ WebSocket Streaming (25 FPS)         │
│  └─ HTTPS (mkcert, port 443)             │
└────────┬─────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│   mDNS (Avahi) — visitor-analysis.local  │
│   HTTP :80 → HTTPS :443 redirect         │
└────────┬─────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│          Web Dashboard                   │
│  ├─ https://visitor-analysis.local/      │
│  ├─ https://visitor-analysis.local/detect-all
│  ├─ Live Video Feed (25 FPS)             │
│  ├─ Today / Weekly / Monthly / All-time  │
│  ├─ Gender & Age Distribution            │
│  └─ PDF / CSV Export                     │
└──────────────────────────────────────────┘
```

---

## Hardware Requirements

| Component | Minimum | Recommended |
|---|---|---|
| GPU | NVIDIA GTX 1060 6GB | NVIDIA RTX A2000 or better |
| CUDA | 11.8+ | 12.x |
| RAM | 4 GB | 8 GB |
| CPU | 4 cores | 8 cores |
| Python | 3.10+ | 3.12 |

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Object Detection | YOLO26x (Ultralytics 8.4+), FP16, GPU |
| Face Analysis | InsightFace buffalo_l (CUDA), DeepFace |
| ONNX Runtime | onnxruntime-gpu (CUDAExecutionProvider) |
| Storage | SQLite (WAL mode), Atomic JSON writes |
| Auth | Session cookies (HMAC-SHA256) + API key |
| Streaming | WebSocket, JPEG encoding, 25 FPS |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| HTTPS | mkcert (locally trusted CA) |
| mDNS | Avahi daemon (`visitor-analysis.local`) |
| Testing | pytest, httpx, websockets, pytest-asyncio |

---

## Project Structure

```
visitor-analytics-gpu/
├── backend/
│   ├── main.py              # FastAPI app, middleware, auth, endpoints, YOLO26 explorer
│   ├── config.py            # Configuration from environment
│   ├── cctv_handler.py      # CCTV camera connection (RTSP)
│   ├── detection.py         # YOLO26 + InsightFace + DeepFace + VisitorTracker
│   ├── streaming.py         # WebSocket video streaming (async parallel face analysis)
│   ├── data_storage.py      # SQLite statistics persistence
│   ├── pdf_report.py        # PDF report generation (ReportLab)
│   ├── visitor_state.py     # Visitor state persistence + encryption
│   └── atomic_write.py      # Safe file writing utilities
├── frontend/
│   ├── index.html           # Dashboard UI
│   ├── login.html           # Login page
│   └── detect-all.html      # YOLO26 all-classes explorer
├── static/
│   ├── css/style.css        # Dark theme styling
│   └── js/app.js            # Dashboard logic
├── certs/                   # SSL certificates (mkcert, not committed)
├── tests/                   # 84 automated tests
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
YOLO_MODEL=yolo26x.pt
CONFIDENCE_THRESHOLD=0.4
STREAM_FPS=25
JPEG_QUALITY=90
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
| `https://visitor-analysis.local/detect-all` | YOLO26 all-classes explorer |
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
| `CONFIDENCE_THRESHOLD` | Person detection confidence (0.1–0.95) | `0.4` |
| `GENDER_ENABLED` | Enable gender/age detection | `true` |
| `YOLO_MODEL` | YOLO model file | `yolo26x.pt` |

### Streaming

| Variable | Description | Default |
|---|---|---|
| `STREAM_FPS` | Streaming frame rate | `25` |
| `JPEG_QUALITY` | JPEG quality (0–100) | `90` |

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

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/` | GET | Session | Dashboard UI |
| `/detect-all` | GET | — | YOLO26 all-classes explorer |
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
| `/ws/stream` | WebSocket | Yes | Live video feed |
| `/ws/detect-all` | WebSocket | — | YOLO26 all-classes stream |
| `/rootCA.pem` | GET | — | Download CA certificate |
| `/proxy.pac` | GET | — | Proxy auto-config (PAC) |

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
| Audit Trail | Every request logged with IP, method, path, status, duration |

---

## Performance (NVIDIA RTX A2000)

| Metric | Value |
|---|---|
| Stream FPS | 25 |
| Detection rate | ~12 detections/sec (YOLO26x + imgsz=1280) |
| GPU VRAM | ~1.4 GB |
| GPU Utilisation | 20–60% |
| Face analysis | Parallel async (all faces per frame simultaneously) |
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
| Low FPS | Increase `detection_interval` in `streaming.py` or use a smaller model (`yolo26l.pt`) |
| Camera not connecting | Check RTSP URL and ensure camera is on the same network |
| GPU not used | Verify `nvidia-smi` shows the process; ensure `onnxruntime-gpu` is installed |
| All gender "Unknown" | Ensure people face camera with adequate lighting |
| Stats lost after restart | Set `SESSION_SECRET` in `.env` |

---

## Privacy & Compliance

- No video recording — all analysis is real-time only
- No face images stored — only 512-dimensional numerical embeddings
- Anonymous statistics only — no personally identifiable information
- Embeddings cleared after 30 minutes of inactivity
- Optional Fernet encryption for embeddings at rest
- Old data auto-deleted after 365 days (configurable)

---

## License

Developed by **Bahagian Transformasi Digital**.

Built with:
- [Ultralytics YOLO26](https://docs.ultralytics.com/models/yolo26/)
- [InsightFace](https://github.com/deepinsight/insightface)
- [DeepFace](https://github.com/serengil/deepface)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenCV](https://opencv.org/)
- [mkcert](https://github.com/FiloSottile/mkcert)
