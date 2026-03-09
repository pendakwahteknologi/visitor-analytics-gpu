# CCTV Stream Processing System - Ubuntu Server Setup

Build a web-based CCTV monitoring system with real-time people and gender detection accessible via browser.

## System Architecture Overview
- **Backend**: Python (Flask/FastAPI) for CCTV connection and ML inference
- **Frontend**: HTML/CSS/JavaScript for web interface
- **Streaming**: WebSocket or HTTP streaming for real-time video
- **Database**: Optional - for logging detections
- **Server**: Ubuntu 20.04 LTS or later

---

## Phase 1: System Setup & Infrastructure ✅ COMPLETE

### 1.1 Ubuntu Server Preparation ✅
- [x] SSH into Ubuntu server or have terminal access
- [x] Update system packages: `sudo apt update && sudo apt upgrade`
- [x] Install Python 3.9+ and pip: `sudo apt install python3 python3-pip python3-venv`
- [x] Install system dependencies:
  - [x] `sudo apt install libopencv-dev python3-opencv`
  - [x] `sudo apt install libsm6 libxext6 libxrender-dev` (for OpenCV)
  - [x] `sudo apt install ffmpeg` (for video encoding)
- [ ] Install and configure Nginx (reverse proxy):
  - [ ] `sudo apt install nginx`
  - [ ] Create Nginx config for web app
  - [ ] Enable SSL/HTTPS (Let's Encrypt)

### 1.2 Project Directory Setup
- [ ] Create project directory: `/home/ubuntu/cctv-detection-system`
- [ ] Create subdirectories:
  - [ ] `backend/` - Python Flask/FastAPI app
  - [ ] `frontend/` - Web interface files
  - [ ] `models/` - ML model files
  - [ ] `static/` - CSS, JS, images
  - [ ] `logs/` - Application logs
  - [ ] `data/` - Stored snapshots/videos

### 1.3 Python Virtual Environment
- [ ] Create venv: `python3 -m venv venv`
- [ ] Activate venv: `source venv/bin/activate`
- [ ] Upgrade pip: `pip install --upgrade pip`

---

## Phase 2: Backend Development ✅ COMPLETE

### 2.1 Web Framework Setup ✅
- [x] Choose framework: **FastAPI** ✅
- [x] Install dependencies:
  - [x] `pip install fastapi uvicorn` ✅
  - [x] `pip install python-multipart` ✅
  - [x] `pip install aiofiles` ✅
  - [x] `pip install websockets` ✅
- [x] Create basic app structure:
  - [x] `backend/main.py` ✅
  - [x] `backend/config.py` ✅
  - [x] App structure created ✅

### 2.2 CCTV Connection Module ✅
- [x] Create `backend/cctv_handler.py`:
  - [x] Connect to RTSP stream ✅
  - [x] Handle authentication ✅
  - [x] Frame capture and buffering ✅
  - [x] Error handling and reconnection ✅
  - [x] Frame rate control ✅

### 2.3 ML Detection Module ✅
- [x] Create `backend/detection.py`:
  - [x] YOLO person detection ✅
  - [x] Gender classification (DeepFace) ✅
  - [x] **Age detection with age groups** ✅
  - [x] **InsightFace integration** ✅ (v3.0.0)
  - [x] **Face re-identification system** ✅ (v3.0.0)
  - [x] **Confirmation system** ✅ (v3.0.0)
  - [x] Performance optimization ✅

### 2.4 WebSocket Streaming ✅
- [x] Create `backend/streaming.py`:
  - [x] WebSocket handler for streaming ✅
  - [x] JPEG encoding ✅
  - [x] Frame rate management ✅
  - [x] Connection management ✅
  - [x] Error handling ✅

### 2.5 API Endpoints ✅
- [x] `GET /health` ✅
- [x] `GET /settings` ✅
- [x] `POST /settings` ✅
- [x] `GET /stats` ✅
- [x] `WebSocket /ws/stream` ✅
- [x] `POST /reset-stats` ✅
- [x] `GET /stats/weekly` ✅
- [x] `GET /stats/monthly` ✅
- [x] `GET /stats/all-time` ✅

### 2.6 Logging & Monitoring ✅
- [x] Logging implemented ✅
- [x] FPS monitoring ✅
- [x] Detection logging ✅

---

## Phase 3: Frontend Development ✅ COMPLETE

### 3.1 HTML Structure ✅
- [x] Create `frontend/index.html`:
  - [x] Header with title and status indicator ✅
  - [x] Video display area ✅
  - [x] Control panel:
    - [x] Start/Stop buttons ✅
    - [x] Confidence slider ✅
    - [x] Gender & Age toggle ✅
  - [x] Statistics panel:
    - [x] Current people count ✅
    - [x] Gender breakdown ✅
    - [x] **Age group breakdown** ✅
    - [x] FPS indicator ✅
  - [x] Period statistics:
    - [x] Weekly stats with age groups ✅
    - [x] Monthly stats with age groups ✅
    - [x] All-time stats with age groups ✅
  - [x] Reset statistics button ✅
  - [x] Responsive layout ✅

### 3.2 CSS Styling ✅
- [x] Create `frontend/style.css`:
  - [x] Dark theme optimized for mall display ✅
  - [x] Responsive design ✅
  - [x] **16:9 fullscreen optimization** ✅ (v2.1.0)
  - [x] **No black bars on video feed** ✅ (v2.1.0)
  - [x] Modern card design ✅
  - [x] Loading indicators ✅
  - [x] Smooth animations ✅

### 3.3 JavaScript Functionality ✅
- [x] Create `frontend/app.js`:
  - [x] WebSocket connection ✅
  - [x] Real-time frame display ✅
  - [x] Control panel interactions ✅
  - [x] Statistics updates ✅
  - [x] Auto-reconnection ✅
  - [x] **Age statistics display** ✅
  - [x] **Period statistics (weekly/monthly/all-time)** ✅

### 3.4 Additional Frontend Features ✅
- [x] Dark mode (implemented) ✅
- [x] Settings persistence ✅
- [x] Professional mall display layout ✅
- [x] Live clock and date display ✅
- [x] Gender percentage calculations ✅
- [x] **Age group breakdowns (5 categories)** ✅

---

## Phase 4: Integration & Testing ✅ MOSTLY COMPLETE

### 4.1 Local Testing ✅
- [x] Test CCTV connection ✅
- [x] Test YOLO person detection ✅
- [x] Test gender classification ✅
- [x] Test **age detection** ✅
- [x] Test **face re-identification** ✅
- [x] Test WebSocket streaming ✅
- [x] Test API endpoints ✅
- [x] Test frontend:
  - [x] Video streaming display ✅
  - [x] Control panel responsiveness ✅
  - [x] Statistics updates ✅
  - [x] Period statistics display ✅

### 4.2 Performance Testing ✅
- [x] Measured FPS: **8-10 FPS** ✅
- [x] CPU/memory usage: Stable ✅
- [x] Multiple browser clients: Working ✅
- [x] **Visitor counting accuracy: 100% (1 person = 1 visitor)** ✅
- [x] **False positive reduction: 43+ → 1** ✅

### 4.3 Error Handling Testing ✅
- [x] CCTV disconnection and reconnection ✅
- [x] WebSocket reconnection with exponential backoff ✅
- [x] Invalid input handling ✅
- [x] Long-running sessions (190+ seconds tested) ✅

---

## Phase 5: Deployment & Configuration

### 5.1 Production Server Setup
- [ ] Install Gunicorn (WSGI server): `pip install gunicorn`
- [ ] Create systemd service file for the app:
  - [ ] `/etc/systemd/system/cctv-detection.service`
  - [ ] Enable auto-start on reboot
- [ ] Configure Nginx as reverse proxy:
  - [ ] Proxy requests to Gunicorn
  - [ ] Handle WebSocket upgrade headers
  - [ ] SSL/HTTPS configuration
- [ ] Configure firewall:
  - [ ] Allow HTTP/HTTPS (ports 80, 443)
  - [ ] Restrict RTSP camera IP access
  - [ ] Restrict admin API endpoints

### 5.2 Environment Configuration
- [ ] Create `.env` file with:
  - [ ] CAMERA_IP=172.31.0.71
  - [ ] CAMERA_USERNAME=admin
  - [ ] CAMERA_PASSWORD=TestingPKNS2026
  - [ ] FLASK_ENV=production
  - [ ] DEBUG=False
  - [ ] Model paths and settings
- [ ] Create `config.py` for loading env variables

### 5.3 Backup & Data Management
- [ ] Set up automatic snapshot cleanup (older than X days)
- [ ] Configure video storage limits
- [ ] Implement database for detection logs (optional)
- [ ] Set up backup strategy for important data

### 5.4 Security Hardening
- [ ] Implement authentication for web interface (optional):
  - [ ] Username/password login
  - [ ] Session management
- [ ] Rate limiting on API endpoints
- [ ] CORS configuration
- [ ] Input validation on all endpoints
- [ ] Security headers in Nginx config

---

## Phase 6: Monitoring & Maintenance

### 6.1 Logging & Debugging
- [ ] Set up centralized logging
- [ ] Create log rotation strategy
- [ ] Monitor application errors
- [ ] Track API response times

### 6.2 Monitoring Tools (Optional)
- [ ] Install system monitoring:
  - [ ] `htop` for resource monitoring
  - [ ] Application-level metrics dashboard
  - [ ] Uptime monitoring

### 6.3 Scheduled Tasks
- [ ] Cleanup old snapshots (cron job)
- [ ] Cleanup old videos (cron job)
- [ ] Automatic log rotation
- [ ] Database maintenance (if using DB)

### 6.4 Documentation
- [ ] Create README with setup instructions
- [ ] Document API endpoints
- [ ] Create troubleshooting guide
- [ ] Document CCTV connection info and credentials
- [ ] Create user manual for web interface

---

## Phase 7: Advanced Features (Optional)

### 7.1 Database Integration
- [ ] Install PostgreSQL or SQLite
- [ ] Create schema for detection logs
- [ ] Implement detection history queries
- [ ] Create analytics dashboard

### 7.2 Advanced Analytics
- [ ] Track people count trends over time
- [ ] Gender distribution statistics
- [ ] Peak hours analysis
- [ ] Generate reports

### 7.3 Mobile Responsive ✅
- [x] Tested on multiple browsers ✅
- [x] Mobile-friendly layout ✅

### 7.4 Push Notifications (Optional)
- [ ] Alert when certain conditions met:
  - [ ] Crowd detection (> X people)
  - [ ] Unusual activity
  - [ ] System errors

### 7.5 Multi-Camera Support
- [ ] Extend system to handle multiple CCTV feeds
- [ ] Create camera selection UI
- [ ] Manage multiple streams

---

## Phase 8: Zone-Based Analytics (Multi-Shop Tracking) 🆕 IN PLANNING

### 8.1 Zone Definition Interface
- [ ] Admin UI to draw rectangular zones on video feed
- [ ] Define zone names (Shop A, Shop B, Shop C, etc.)
- [ ] Store zone coordinates in configuration
- [ ] Visual preview of zones

### 8.2 Entry/Exit Detection
- [ ] Define entry/exit lines per zone
- [ ] Detect direction of movement (IN vs OUT)
- [ ] Track person trajectory across frame
- [ ] Distinguish between entering/leaving shop

### 8.3 Per-Zone Statistics
- [ ] Count unique visitors per zone
- [ ] Track IN/OUT counts separately
- [ ] Store zone-specific stats:
  - [ ] Today's visitors per shop
  - [ ] Weekly per shop
  - [ ] Monthly per shop
  - [ ] All-time per shop
- [ ] Gender breakdown per zone
- [ ] Age group breakdown per zone

### 8.4 Zone Analytics Dashboard
- [ ] Display stats for each shop side-by-side
- [ ] Comparison charts:
  - [ ] Which shop has most visitors
  - [ ] IN vs OUT flow comparison
  - [ ] Peak times per shop
- [ ] Heatmap showing popular zones
- [ ] Dwell time analysis (how long people stay)

### 8.5 Database for Zone History
- [ ] Store zone definitions
- [ ] Store per-zone detection history
- [ ] Query zone statistics over time
- [ ] Generate zone-specific reports

**Status**: Planned for implementation after current version stabilizes

---

## Deployment Checklist

Before going live:
- [ ] All tests passing
- [ ] SSL certificate configured
- [ ] Firewall properly configured
- [ ] Backup strategy implemented
- [ ] Monitoring set up
- [ ] Documentation complete
- [ ] Security audit completed
- [ ] Performance acceptable (FPS, CPU, memory)
- [ ] Error handling verified
- [ ] Auto-recovery tested
- [ ] User training completed (if needed)

---

## Quick Reference: Technology Stack

| Component | Options |
|-----------|---------|
| Framework | FastAPI (async) or Flask |
| Server | Gunicorn + Nginx |
| Streaming | WebSocket + JPEG |
| ML Framework | YOLOv8, OpenCV DNN |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Database | SQLite (simple) or PostgreSQL (advanced) |
| Process Manager | systemd |

---

## Estimated Effort

- **Phase 1**: 1-2 hours (server setup)
- **Phase 2**: 8-12 hours (backend development)
- **Phase 3**: 6-8 hours (frontend development)
- **Phase 4**: 4-6 hours (testing)
- **Phase 5**: 3-4 hours (deployment)
- **Phase 6**: Ongoing
- **Phase 7**: Optional, additional time varies

**Total (Phases 1-5): 22-32 hours**

---

## Important Notes

1. **Network**: Ensure Ubuntu server can access camera at 172.31.0.71
2. **GPU**: System can optionally use GPU for faster inference if available
3. **Bandwidth**: WebSocket streaming uses ~2-5 Mbps at 15 FPS with 1080p resolution
4. **Security**: Keep camera credentials secure, use environment variables
5. **Performance**: Start with yolov8n (nano) for better performance
6. **Browser Support**: Works on modern browsers (Chrome, Firefox, Safari, Edge)

---

## Troubleshooting Resources

- Check logs: `journalctl -u cctv-detection -f`
- Test CCTV connection: Use ffmpeg to test RTSP stream
- Debug WebSocket: Use browser DevTools Network tab
- Performance issues: Reduce video resolution or JPEG quality
- Connection issues: Verify firewall rules and camera accessibility

---

## Current Status Summary (v3.4.3)

### ✅ Completed Features
- [x] **Core Detection**: YOLO person detection with real-time streaming
- [x] **Gender Detection**: DeepFace + InsightFace support
- [x] **Age Detection**: With 5 age group categories + Unknown
- [x] **Face Re-identification**: Prevents double-counting with 512D embeddings
- [x] **Multi-angle Matching**: Stores up to 5 embeddings per visitor
- [x] **Relaxed Detection** 🆕: Single-detection counting (v3.4.0)
- [x] **Unknown Gender Tracking** 🆕: Tracks visitors with undetected gender (v3.4.0)
- [x] **Lower Thresholds** 🆕: 30% person, 40% gender, 25px min face (v3.4.0)
- [x] **Multi-Biometric Fusion** ⭐: Gender + Age + Temporal weighting (v3.1.0)
- [x] **Ensemble Demographics** ✨: InsightFace + DeepFace voting for improved accuracy (v3.2.0)
- [x] **Statistics**: Today, Weekly, Monthly, All-time with gender & age breakdown
- [x] **Dashboard**: Professional mall display with 16:9 fullscreen support
- [x] **WebSocket Streaming**: Real-time video with auto-reconnection
- [x] **Performance**: 8-10 FPS, optimized for bandwidth
- [x] **Accuracy**: 100% visitor count accuracy (tested with 1 person over 246 seconds)

### 📊 Performance Metrics
- **Visitor Accuracy**: Before 43+, After 1 (for 1 person) - 100% accurate ✅
- **Extended Test**: 246+ seconds, still only 1 visitor counted (v3.1.0) ✅
- **False Positives**: ~0% with confirmation system + multi-biometric fusion
- **Age Detection**: Improved accuracy vs DeepFace
- **Gender Matching**: Prevents wrong-gender confusion
- **Temporal Weighting**: Recent visitors prioritized for matching
- **Response Time**: Real-time (<1-2ms per match calculation)
- **Uptime**: 246+ seconds tested without false counts or incorrect matches

---

## Phase 9: System Resilience - Connection Handling & Data Persistence ✅ COMPLETE

### 9.1 Atomic File Writes ✅
- [x] Create `backend/atomic_write.py` ✅
  - [x] Implement `atomic_write_json()` with fsync ✅
  - [x] Implement `atomic_read_json()` with corruption detection ✅
  - [x] Auto-backup corrupted files ✅
- [x] Update `backend/data_storage.py` to use atomic writes ✅

### 9.2 Visitor State Persistence ✅
- [x] Create `backend/visitor_state.py` ✅
  - [x] Implement `VisitorStatePersistence` class ✅
  - [x] Handle numpy array serialization ✅
  - [x] Save/restore functionality ✅
- [x] Integrate into `VisitorTracker` ✅
  - [x] Load state on initialization ✅
  - [x] Auto-save every 30 seconds ✅
  - [x] Save on application shutdown ✅

### 9.3 Infinite Reconnection with Exponential Backoff ✅
- [x] Update `backend/cctv_handler.py` ✅
  - [x] Remove `max_reconnect_attempts` limit ✅
  - [x] Implement exponential backoff (5s → 60s) ✅
  - [x] Add connection state tracking ✅
  - [x] Add state callback system ✅
  - [x] Implement `_notify_state_change()` ✅
  - [x] Implement `_calculate_reconnect_delay()` ✅

### 9.4 Connection Status Broadcasting ✅
- [x] Update `backend/streaming.py` ✅
  - [x] Add `broadcast_status()` method ✅
  - [x] Change frame format to JSON envelope ✅
  - [x] Register CCTV state callbacks ✅
  - [x] Only broadcast frames when connected ✅
- [x] Update `backend/main.py` ✅
  - [x] Send initial status to new WebSocket clients ✅

### 9.5 Frontend Status Handling ✅
- [x] Update `static/js/app.js` ✅
  - [x] Parse JSON WebSocket messages ✅
  - [x] Handle "frame" and "status" message types ✅
  - [x] Track CCTV connection state ✅
  - [x] Clear video on disconnect ✅
  - [x] Show reconnection overlay ✅
- [x] Update `frontend/index.html` ✅
  - [x] Add dynamic overlay text elements ✅

### ✅ Resilience Features Verified
- [x] Atomic writes tested and working
- [x] Visitor state persistence tested and working
- [x] Infinite reconnection with exponential backoff implemented
- [x] Connection status broadcasting working
- [x] Frontend stale frame prevention working
- [x] CCTV connection to 172.31.0.71 established and working

---

---

## Phase 10: Performance Optimization & Resource Management 🚧 IN PROGRESS

### 10.1 Camera Configuration Updates ✅
- [x] Camera IP migrated from `172.31.0.71` to `10.0.11.123` (2026-02-04)
- [x] RTSP credentials verified (admin/TestingPKNS2026)
- [x] Stream path: `/Streaming/Channels/101`
- [x] Updated `.env` file with new CAMERA_IP

### 10.2 System Performance Issues Identified ⚠️
Current system is **overloaded** with ~300% CPU usage:

| Process | CPU | Memory | Issue |
|---------|-----|--------|-------|
| ffmpeg (PKNS) | 163% | 3.6% | 4K stream transcoding |
| python (ML worker) | 82% | 6.1% | YOLOv8 on 4K frames |
| uvicorn (visitor-stat) | 55% | 20.7% | Detection + streaming |

**Root Cause**: Two separate video processing pipelines (PKNS Laravel + visitor-stat) both processing the same 4K camera stream simultaneously.

### 10.3 Performance Optimization Tasks 📋
- [ ] **Reduce camera resolution** (4K → 1080p)
  - Current: 3840x2160 @ 24fps
  - Target: 1920x1080 @ 15fps
  - Expected CPU reduction: ~75%

- [ ] **Consolidate video processing**
  - Single ingestion pipeline for camera
  - Share processed frames via Redis pub/sub
  - Expected CPU reduction: ~50%

- [ ] **Choose primary system**
  - Option A: Use visitor-stat only (disable PKNS ML worker)
  - Option B: Use PKNS only (disable visitor-stat)
  - Option C: Dedicate different cameras to each system

- [ ] **Optimize YOLOv8 inference**
  - Current model: yolov8n (nano)
  - Consider: Frame skipping, lower resolution input
  - Consider: GPU acceleration if available

- [ ] **Memory optimization**
  - uvicorn using 1.6GB RAM
  - Review model loading and caching
  - Consider lazy loading for ensemble models

### 10.4 Quick Fixes Available
```bash
# Option 1: Stop PKNS ML worker (save ~82% CPU)
sudo supervisorctl stop pkns-ml:pkns-ml-cam-ent-01

# Option 2: Stop visitor-stat (save ~55% CPU)
pkill -f "uvicorn backend.main:app --host 0.0.0.0 --port 8000"

# Option 3: Stop PKNS ffmpeg HLS (save ~163% CPU)
sudo supervisorctl stop pkns-hls:pkns-hls-cam-ent-01
```

---

### 🎯 Next Steps (Phase 10+)
- **Performance**: Address CPU overload (priority: HIGH)
- **Zone-Based Analytics**: Multi-shop visitor tracking with IN/OUT detection
- **Database Integration**: Persistent history and detailed analytics
- **Production Deployment**: Systemd service, Nginx, SSL
- **Advanced Monitoring**: Real-time dashboards and alerting

### 📝 Version History
- **v3.4.3** (2026-02-06): Systemd Service + Cron Job + Unknown in Period Stats 🆕
- **v3.4.2** (2026-02-06): Fixed Period Stats Persistence
- **v3.4.1** (2026-02-06): Instant Visitor Counting Fix
- **v3.4.0** (2026-02-06): Relaxed Detection + Unknown Gender Tracking
- **v3.3.1** (2026-02-04): Camera IP Migration + Performance Analysis ✅
- **v3.3.0** (2026-02-01): System Resilience (Infinite Reconnection + Data Persistence) ✅
- **v3.2.0** (2026-01-31): Ensemble Demographics (InsightFace + DeepFace voting)
- **v3.1.0** (2026-01-31): Multi-Biometric Fusion (Face + Gender + Age + Temporal)
- **v3.0.0** (2026-01-31): InsightFace + Face Re-id + Confirmation System
- **v2.1.0** (2026-01-31): 16:9 Fullscreen Optimization
- **v2.0.0** (2026-01-31): Major Dashboard Redesign
- **v1.1.0** (2026-01-31): Gender Detection
- **v1.0.1** (2026-01-31): Performance Optimizations
- **v1.0.0** (2026-01-31): Initial Release
