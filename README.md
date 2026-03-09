# Visitor Analytics

Real-time CCTV-based visitor counting system with gender and age detection, powered by YOLOv8 and face analysis models.

![Version](https://img.shields.io/badge/version-3.4.3-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Real-time Person Detection** - YOLOv8n for fast and accurate person detection
- **Gender Classification** - Ensemble approach using DeepFace + InsightFace
- **Age Detection** - 5 age groups (Children, Teens, Young Adults, Adults, Seniors)
- **Face Re-identification** - Prevents double-counting using face embeddings and cosine similarity
- **Live Video Stream** - WebSocket-based streaming with JPEG encoding
- **Modern Dashboard** - Dark-themed responsive UI optimized for large displays
- **Privacy First** - No video recording or face storage; real-time analysis only

---

## System Architecture

```
┌─────────────────┐
│   CCTV Camera   │  RTSP Stream
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Python Server  │
│  ├─ YOLOv8n (Person Detection)
│  ├─ InsightFace + DeepFace (Demographics)
│  └─ FastAPI + WebSocket
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Web Dashboard  │
│  ├─ Live Video Feed
│  ├─ Visitor Statistics
│  └─ Controls & Settings
└─────────────────┘
```

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| ML Models | YOLOv8n, DeepFace, InsightFace |
| Deep Learning | PyTorch, TensorFlow |
| Computer Vision | OpenCV |
| Streaming | WebSocket, JPEG encoding |
| Frontend | HTML5, CSS3, Vanilla JavaScript |

---

## Project Structure

```
visitor-analytics/
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration from environment
│   ├── cctv_handler.py      # CCTV camera connection (RTSP)
│   ├── detection.py         # YOLOv8 + DeepFace + InsightFace
│   ├── streaming.py         # WebSocket video streaming
│   ├── data_storage.py      # Statistics persistence
│   ├── visitor_state.py     # Visitor state management
│   └── atomic_write.py      # Safe file writing utilities
├── frontend/
│   └── index.html           # Dashboard UI
├── static/
│   ├── css/style.css        # Dark theme styling
│   └── js/app.js            # Dashboard logic
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── run.sh                   # Startup script
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

   Edit `.env` with your camera IP, RTSP URL, and preferred settings.

5. **Download YOLOv8 model**

   The YOLOv8n model will be downloaded automatically on first run, or you can download it manually:

   ```bash
   pip install ultralytics
   python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
   ```

6. **Start the server**

   ```bash
   ./run.sh
   ```

   Or manually:

   ```bash
   cd backend
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

7. **Open the dashboard**

   Navigate to `http://localhost:8000` in your browser.

---

## Configuration

All configuration is done via environment variables in the `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `CAMERA_IP` | CCTV camera IP address | - |
| `CAMERA_USERNAME` | Camera login username | - |
| `CAMERA_PASSWORD` | Camera login password | - |
| `CAMERA_RTSP_URL` | Full RTSP stream URL | - |
| `CONFIDENCE_THRESHOLD` | Person detection confidence (0-1) | `0.5` |
| `GENDER_ENABLED` | Enable gender/age detection | `true` |
| `GENDER_THRESHOLD` | Gender detection confidence (0-1) | `0.6` |
| `YOLO_MODEL` | YOLO model file | `yolov8n.pt` |
| `STREAM_FPS` | Streaming frame rate | `15` |
| `JPEG_QUALITY` | JPEG compression quality (0-100) | `65` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/health` | GET | Health check |
| `/settings` | GET/POST | Get or update settings |
| `/stats` | GET | Current visitor statistics |
| `/stats/weekly` | GET | Weekly statistics |
| `/stats/monthly` | GET | Monthly statistics |
| `/stats/all-time` | GET | All-time statistics |
| `/stream/start` | POST | Start CCTV monitoring |
| `/stream/stop` | POST | Stop CCTV monitoring |
| `/ws/stream` | WebSocket | Live video feed |
| `/reset-stats` | POST | Reset statistics |

---

## How It Works

### Visitor Counting Pipeline

1. **Person Detection** - YOLOv8n identifies people in each frame
2. **Face Analysis** - InsightFace + DeepFace ensemble extracts gender, age, and face embeddings
3. **Re-identification** - Multi-biometric fusion (face 60% + gender 20% + age 10% + temporal 10%) prevents double-counting
4. **Statistics** - Unique visitor counts, gender/age breakdowns, stored with atomic writes for crash safety

### Performance

| Metric | Value |
|--------|-------|
| Detection FPS | 12-15 |
| Latency | < 500ms |
| Bandwidth | 2-3 Mbps |
| CPU Usage | 40-60% |
| Memory | ~2 GB |

---

## Privacy & Compliance

- No video recording - all analysis is done in real-time
- No face images stored - only numerical embeddings for re-identification during the session
- Anonymous statistics only - no personally identifiable information
- Embeddings are cleared after 30 minutes of inactivity

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Video not showing | Ensure camera is reachable and "Start Monitoring" is clicked |
| Low FPS (< 10) | Disable gender detection or check server CPU usage |
| All gender "Unknown" | Ensure people face the camera with good lighting |
| Connection drops | System auto-reconnects with exponential backoff |

---

## License

This project is developed by **Bahagian Transformasi Digital**.

Built with:
- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- [DeepFace](https://github.com/serengil/deepface)
- [InsightFace](https://github.com/deepinsight/insightface)
- [FastAPI](https://fastapi.tiangolo.com/)
- [OpenCV](https://opencv.org/)
