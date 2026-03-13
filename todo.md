# Visitor Analytics — Production Hardening Roadmap

Current state: The system works and is deployed, but has gaps that will cause problems under
sustained 24/7 unattended operation. This document covers what to fix, in priority order.

Server: Ubuntu 22.04 LTS, RTX A2000 (6 GB VRAM), 32 GB RAM, 410 GB disk
Stack: FastAPI + Uvicorn, YOLO + InsightFace + OSNet, plain HTTP on port 80

---

## Priority 1 — Fix Before Leaving Unattended

These are bugs or gaps that will cause service degradation or data loss within days of
continuous 24/7 operation.

### 1.1 Shutdown saves state before streams actually stop
- `main.py` lifespan calls `body_tracker.save_state()` then `stream_manager.stop_streaming()`
- The streaming loop may still be writing new persons while state is being saved
- Fix: stop streaming first, wait for it to fully halt, then save state
- Risk if not fixed: visitor count drift across restarts

### 1.2 Pending visitors never get garbage collected when OSNet is down
- `BodyReIDTracker._evict_expired()` only runs when `body_embedding is not None`
- If OSNet crashes at runtime, pending dict grows forever (one entry per detection)
- Fix: call `_evict_expired()` unconditionally on every `check_person()` call
- Risk if not fixed: memory leak, slow dict lookups over hours

### 1.3 Midnight cleanup races with active capture writes
- `clear_all()` on face/person stores deletes files and rewrites index.json
- The streaming loop may be writing a new capture at the same time
- Fix: acquire store lock before clearing, or pause detection during cleanup
- Risk if not fixed: corrupted index.json, orphaned JPEG files

### 1.4 No disk space checks before writing captures
- `person_capture_store.py` and `face_capture_store.py` write JPEG files without
  checking available space
- If disk fills, `cv2.imencode()` or `open().write()` throws, potentially crashing the
  detection loop
- Fix: check `os.statvfs()` before save, skip writes with a warning if below threshold
- Risk if not fixed: detection loop crash on full disk, service keeps restarting

### 1.5 Rate limiter buckets accumulate forever
- `RateLimiter._buckets` dict stores one entry per client IP, never evicts
- Fix: add a periodic sweep that removes buckets not accessed in 1 hour
- Risk if not fixed: slow memory leak (low urgency unless exposed to public internet)

---

## Priority 2 — Production Stability

These make the difference between "works most of the time" and "runs reliably for months."

### 2.1 Run service as non-root user
- `visitor-analytics.service` uses `User=root` — any FastAPI exploit gives full system access
- Can't bind port 80 without root
- Fix: run uvicorn on port 8000, add nginx as reverse proxy on port 80 with WebSocket support
- Alternative: use `CAP_NET_BIND_SERVICE` capability to allow binding port 80 without root

### 2.2 Add systemd resource limits
- No `MemoryMax`, `CPUQuota`, or `TasksMax` in the service file
- A runaway process can exhaust all 32 GB RAM and take the server down
- Fix: add to `[Service]`:
  ```
  MemoryMax=12G
  TasksMax=512
  ```

### 2.3 Hardcoded CUDA library path is fragile
- `LD_LIBRARY_PATH` in service file references `python3.12` explicitly
- Breaks silently if Python is upgraded to 3.13+
- Fix: use `$(python -c "import nvidia.cublas; print(nvidia.cublas.__path__[0])")` in
  an `ExecStartPre` script, or rely on the nvidia wheel's built-in ld config

### 2.4 GPU OOM handling
- If YOLO or InsightFace hits GPU OOM, `run_in_executor()` catches the exception but
  detection silently returns empty results
- Users see zero detections with no explanation
- Fix: catch `torch.cuda.OutOfMemoryError` explicitly, log it as CRITICAL, set a
  health flag, surface it in `/health` endpoint and frontend status

### 2.5 SQLite contention under load
- `data_storage.py` uses `timeout=10` for SQLite
- Stats API + streaming save loop + midnight cleanup can contend for the lock
- Fix: increase timeout to 30s, ensure WAL mode is enabled (verify with PRAGMA check),
  consider using a connection pool or async SQLite driver

### 2.6 OSNet crash silently disables Re-ID
- If OSNet fails at runtime (not just at init), the system falls through to `_count_only()`
  which counts every YOLO detection as a unique visitor
- Fix: add explicit monitoring of `osnet.available`, log when it transitions to False,
  surface in `/health` endpoint
- Consider: refuse to count visitors at all when Re-ID is down, rather than inflating counts

---

## Priority 3 — Observability & Operations

Without these, problems happen silently and you only find out when someone complains.

### 3.1 Health endpoint should fail when models aren't working
- Current `/health` always returns `"status": "healthy"` even if YOLO failed to load
- Fix: return `"status": "degraded"` when any model is not loaded, or when GPU is OOM,
  or when OSNet is unavailable

### 3.2 Add structured metrics logging
- Log model inference latency, frame processing time, WebSocket queue depth, GPU memory
- Format: structured JSON lines or Prometheus-compatible format
- Enables alerting on performance regression (e.g., inference time doubles)

### 3.3 Watchdog for detection stalls
- If the CCTV feed is connected but no detections happen for 30+ minutes during business
  hours, something is likely wrong (model crashed, GPU hung)
- Fix: add a watchdog timer in the streaming loop that logs a WARNING if no detection
  result is produced in N minutes

### 3.4 External uptime monitoring
- No monitoring exists today — if the service crashes and can't restart (hit
  `StartLimitBurst`), nobody gets notified
- Fix: set up a simple HTTP check from another machine (cron curl to `/health`, alert on
  failure), or use an external service like Uptime Kuma

### 3.5 Log rotation for application logs
- Rotating file handler is configured (10 MB x 5 backups) — this is fine
- systemd journal handles stdout/stderr — also fine (auto-rotated)
- Verify: `journalctl --disk-usage` to confirm journal isn't growing unbounded

---

## Priority 4 — Performance Improvements

The system runs at 8-10 FPS. These changes can push it higher and improve detection accuracy.

### 4.1 Fix InsightFace GPU acceleration
- InsightFace is forced to CPU due to ONNX Runtime / PyTorch cuBLAS version conflict
- Fixing this makes face analysis 5-10x faster
- Approach: install `onnxruntime-gpu` built for CUDA 12
- Impact: more face analysis samples per person = better gender/age accuracy + higher FPS

### 4.2 Reduce InsightFace det_size
- Currently `(1024, 1024)` — overkill for body crop analysis
- Change to `(640, 640)` for ~2x speedup with minimal accuracy loss

### 4.3 Lower analysis_interval for new persons
- Currently face analysis runs every 4th frame for all persons equally
- New/unknown persons should get analyzed every frame for the first 10 frames, then
  drop back to every 4th frame
- Impact: faster gender/age classification for new visitors

### 4.4 Add gender voting across frames
- Currently one gender prediction sticks permanently
- Accumulate 3-5 predictions per person_id, use majority vote
- Impact: significantly fewer misclassifications

### 4.5 Skip annotation when no WebSocket clients
- Bounding box drawing takes ~2ms/frame, wasted if nobody is watching
- Check `connection_manager.connection_count == 0` before annotating

### 4.6 Reduce YOLO imgsz from 1280 to 640
- Person detection at 640 is still accurate for indoor CCTV
- Halves GPU inference time
- Trade-off: slightly worse detection of small/far persons

---

## Priority 5 — Feature Improvements

Nice-to-have features that add value but aren't critical for stability.

### 5.1 Pin all Python dependencies
- `requirements.txt` has some unpinned or loosely pinned packages
- A `pip install --upgrade` could silently change model behavior
- Fix: pin every dependency to exact version (`package==x.y.z`)

### 5.2 Frontend stats polling backoff
- `fetchStats()` runs every 5s, `fetchPeriodStats()` every 10s, regardless of errors
- If the backend is slow or down, requests pile up
- Fix: double the interval on failure, reset on success

### 5.3 WebSocket reconnection max attempts
- Frontend reconnects indefinitely with 30s max backoff
- After extended backend outage, add a "click to reconnect" button instead of
  perpetual background retries

### 5.4 Person capture tile error handling
- Face tiles show reduced opacity on load error, person tiles show nothing
- Fix: add `onerror` handler to person tiles, show placeholder image

### 5.5 Multi-camera support
- Currently single RTSP stream
- Architecture supports one `CCTVHandler` per camera
- Would need: camera selection UI, per-camera stats, shared GPU inference queue

### 5.6 Zone-based analytics
- Draw zones on video feed (Shop A, Shop B, etc.)
- Track entry/exit per zone using trajectory analysis
- Per-zone visitor counts, gender/age breakdown
- Requires: zone definition UI, trajectory tracking, per-zone storage

### 5.7 Database migration to PostgreSQL
- SQLite works fine at current scale (<1000 visitors/day)
- PostgreSQL would be needed for: multi-camera, zone analytics, concurrent writes
- Only migrate if features demand it — SQLite is simpler to operate

### 5.8 Push notifications / alerting
- Alert on crowd threshold (>N people in frame)
- Alert on system errors (GPU OOM, camera disconnect for >5 min)
- Options: Telegram bot, email, webhook

---

## Session Log — 2026-03-13

### Completed this session

#### Bug Fixes
- **Dashboard hang (critical)** — `BodyGenderAnalyzer.predict()` was blocking the asyncio
  event loop. Moved both call sites to `run_in_executor`. Dashboard now responds instantly.
- **Co-presence identity collision** — Two different people in the same frame were being
  matched as the same person if they had similar body embeddings (similar clothing).
  Fixed with co-presence exclusion: if the matched confirmed person is already active
  under a different track_id in the same frame, skip the match.

#### Counter Improvements (v6.2.0)
- **Unique visitor counter** — counter now increments on Re-ID confirmation only;
  gender/age never blocks a count
- **Track-only Re-ID** — persons too small/far for OSNet embedding tracked by track_id,
  confirmed after 3 sightings, upgraded with real embedding when they walk closer
- **Real-time counter** — dashboard reads live session count; no more 30s lag
- **Immediate DB save** — flush to SQLite the moment a new unique person is confirmed

#### Infrastructure
- **Offline HuggingFace model** — `rizvandwiki/gender-classification-2` pre-downloaded to
  `models/huggingface/`; `HF_HUB_OFFLINE=1` in `.env` — no internet required at runtime
- **GitHub updated** — all active code pushed, stale docs and unused files removed

### Pending — Next Session

#### CCTV Switch to Aneka Walk (BLOCKED — network access)
- `.env` already updated to CAM 1 C1:
  `rtsp://admin:Nais%sic2024@hgw0ad7mecb.sn.mynetname.net:10516/external/stream1`
- **Blocked**: port 10516 connection refused from this server's public IP `175.143.105.193`
- **Action needed**: Aneka Walk network team must whitelist `175.143.105.193` on their
  router/firewall for ports 10516–10562
- Once unblocked: service will auto-connect (no code changes needed)
- 30 cameras total available across 7 switches (see `cctv/CCTV RTSP List for Aneka Walk - Sheet1.pdf`)

#### Verify co-presence fix in production
- Needs 2 people simultaneously in frame to trigger
- Watch for log: `"Co-presence: track X resembles person #Y ... treating as new"`
- If it triggers correctly, both people should be counted within ~2 seconds

---

## Current System Status

| Component        | Status  | Notes                                                        |
|------------------|---------|--------------------------------------------------------------|
| YOLO detection   | Working | yolo26x.pt on GPU, ~7-8 FPS                                  |
| InsightFace      | Working | buffalo_l, CPU (cuBLAS conflict — see 4.1)                   |
| OSNet Re-ID      | Working | CPU, match_threshold=0.60, confirmation_count=3              |
| Body Re-ID       | Working | Track-only fallback for small crops; co-presence exclusion   |
| Visitor counter  | Working | Real-time session count, immediate DB save on new person     |
| CCTV connection  | WAITING | Switched to Aneka Walk CAM 1 C1 — awaiting network access    |
| State persistence| Working | Save on every new visitor + shutdown                         |
| Atomic writes    | Working | fsync + temp file pattern                                    |
| Data storage     | Working | SQLite WAL mode, 10s timeout                                 |
| Capture stores   | Working | 24h rolling cleanup, hourly sweep                            |
| Auth system      | Working | Session cookies + API key                                    |
| WebSocket stream | Working | Auto-reconnect with exponential backoff                      |
| Systemd service  | Working | Auto-restart, 5 attempts per 5 min, port 80                  |
| HuggingFace model| Working | Offline cache, HF_HUB_OFFLINE=1                              |
| Tests            | 15 files | pytest, good coverage of core modules                       |

### Resource Usage (last measured)
- RAM: ~5 GB / 32 GB (16%)
- GPU VRAM: ~809 MB / 6 GB (13%)
- GPU utilization: ~71%
- Disk: 32 GB / 410 GB (8%)
- Server public IP: 175.143.105.193
- Server local IP: 10.0.50.33
