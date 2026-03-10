# Visitor Analytics — TODO

## CRITICAL — Security

- [x] Remove default credentials from `config.py` — require env vars only, no fallback values for CAMERA_IP, CAMERA_USERNAME, CAMERA_PASSWORD
- [x] Add `.env` to `.gitignore` — already present; updated `.env.example` with all new options
- [x] Add authentication middleware to `main.py` — API key auth on all REST and WebSocket endpoints (via API_KEY env var)
- [x] Add CORS configuration to `main.py` — restrict allowed origins (via CORS_ORIGINS env var)
- [x] Add rate limiting middleware to `main.py` — in-memory token bucket per IP (10 req/s, burst 30)
- [x] Sanitize logs in `cctv_handler.py` — RTSP URL credentials masked in all log output
- [x] Add CSP headers to `main.py` — Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy

## HIGH — Statistics Accuracy

- [x] Raise `confirmation_count` from 1 to 3 in `detection.py` — require 3 sightings before counting a visitor
- [x] Raise `CONFIDENCE_THRESHOLD` default from 0.3 to 0.5 in `config.py` — reduce false person detections
- [x] Raise `similarity_threshold` from 0.3 to 0.45 in `detection.py` — prevent merging distinct visitors
- [x] Add minimum face size validation in `detection.py` — reject faces smaller than 40x40 pixels (InsightFace + Ensemble)
- [x] Use median age across sightings in `detection.py` — aggregate via age_observations list on each visitor
- [x] Fix stale detection reuse in `streaming.py` — analysis only runs on fresh detection frames
- [x] Fix `max()` preservation logic in `data_storage.py` — now stores actual counts; reset_today deletes record cleanly

## HIGH — Stability

- [x] Add signal handlers (SIGTERM/SIGINT) in `main.py` — ensure save_state() runs on unexpected shutdown
- [x] Pin dependency versions in `requirements.txt` — changed from >= to ~= (compatible release)
- [x] Cap max active visitors in `detection.py` — limit to 500, evict oldest on overflow
- [x] Add model health check in `main.py` — /health reports YOLO, InsightFace load status + last detection time

## MEDIUM — Code Quality

- [x] Add input validation on `/settings` endpoint in `main.py` — confidence must be 0.1–0.95
- [x] Replace broad `except Exception` with specific exceptions in `detection.py` — catch ValueError, RuntimeError, cv2.error, ImportError, etc. separately
- [x] Add XSS protection in `app.js` — all dynamic content uses _setText (textContent), never innerHTML
- [x] CSRF protection — API key auth serves as CSRF mitigation for state-changing endpoints
- [x] Encrypt face embeddings in `visitor_state.py` — optional Fernet encryption via EMBEDDING_ENCRYPTION_KEY env var
- [x] Add auto-delete for old data in `data_storage.py` — cleanup_old_data runs on startup (default 365 days, configurable)
- [x] Add file logging in `main.py` — RotatingFileHandler with configurable max size and backup count

## LOW — Improvements

- [x] Add unit tests for detection pipeline — 66 tests covering detection utils, visitor tracker, data storage, atomic writes, API, CCTV handler, encryption
- [x] Add integration tests for CCTV reconnection — tested exponential backoff and URL sanitisation
- [x] Add statistics export endpoint in `main.py` — GET /stats/export returns CSV download
- [x] Add cache headers for static assets in `main.py` — Cache-Control: public, max-age=86400 for /static/ paths
- [x] Add request audit logging in `main.py` — AuditLogMiddleware logs IP, method, path, status, duration, key usage
- [x] Migrate from JSON to SQLite in `data_storage.py` — WAL mode, indexed by date, auto-migrates existing JSON on first run

## REMAINING

- [x] Replace broad `except Exception` with specific exceptions in `detection.py`
- [x] Add WebSocket load tests (concurrent clients) — 5 tests: 10 concurrent connections, 20 rapid connect/disconnect, concurrent ping/pong, staggered connections, health check after load
