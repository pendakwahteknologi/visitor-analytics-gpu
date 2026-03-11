import os
import sys
import re
import signal
import logging
import time
import hmac
import cv2
import hashlib
import secrets
import threading
import asyncio
import json as _json
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from datetime import datetime
from collections import defaultdict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    HOST, PORT, DEBUG, CONFIDENCE_THRESHOLD, GENDER_THRESHOLD, GENDER_ENABLED,
    API_KEY, CORS_ORIGINS, LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT,
    ADMIN_USERNAME, ADMIN_PASSWORD, SESSION_SECRET, SESSION_MAX_AGE,
)
from cctv_handler import CCTVHandler
from detection import DetectionEngine
from streaming import StreamManager
from data_storage import DataStorage
from pdf_report import generate_visitor_report

# ---------------------------------------------------------------------------
# Logging — console + rotating file
# ---------------------------------------------------------------------------
log_dir = os.path.dirname(LOG_FILE)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)

log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_level = logging.DEBUG if DEBUG else logging.INFO

logging.basicConfig(level=log_level, format=log_format)

file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
)
file_handler.setFormatter(logging.Formatter(log_format))
file_handler.setLevel(log_level)
logging.getLogger().addHandler(file_handler)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global instances
# ---------------------------------------------------------------------------
cctv_handler = CCTVHandler()
detection_engine = DetectionEngine(gender_threshold=GENDER_THRESHOLD)
detection_engine.set_gender_enabled(GENDER_ENABLED)
data_storage = DataStorage()
stream_manager = StreamManager(cctv_handler, detection_engine, data_storage)

# Track start time
start_time = datetime.now()

# ---------------------------------------------------------------------------
# Rate limiter (simple in-memory token bucket per IP)
# ---------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, requests_per_second: float = 10.0, burst: int = 30):
        self.rate = requests_per_second
        self.burst = burst
        self._buckets: dict = defaultdict(lambda: {"tokens": burst, "last": time.monotonic()})
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets[key]
            elapsed = now - bucket["last"]
            bucket["tokens"] = min(self.burst, bucket["tokens"] + elapsed * self.rate)
            bucket["last"] = now
            if bucket["tokens"] >= 1:
                bucket["tokens"] -= 1
                return True
        return False

rate_limiter = RateLimiter()

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
# Auto-generate a session secret if not configured (stable per process)
_session_secret = SESSION_SECRET or secrets.token_hex(32)


def _create_session_token(username: str) -> str:
    """Create an HMAC-signed session token with expiry."""
    expires = int(time.time()) + SESSION_MAX_AGE
    payload = f"{username}:{expires}"
    sig = hmac.new(_session_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_session_token(token: str) -> str | None:
    """Verify session token. Returns username if valid, None otherwise."""
    if not token:
        return None
    parts = token.rsplit(":", 2)
    if len(parts) != 3:
        return None
    username, expires_str, sig = parts
    try:
        expires = int(expires_str)
    except ValueError:
        return None
    if time.time() > expires:
        return None
    expected_sig = hmac.new(
        _session_secret.encode(), f"{username}:{expires_str}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    return username


def _is_auth_required() -> bool:
    """Auth is required if either API_KEY or ADMIN_PASSWORD is set."""
    return bool(API_KEY) or bool(ADMIN_PASSWORD)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
audit_logger = logging.getLogger("audit")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers including CSP and cache-control to every response."""
    async def dispatch(self, request: Request, call_next):
        # Handle Chrome Private Network Access preflight
        if request.method == "OPTIONS" and "access-control-request-private-network" in request.headers:
            response = Response(status_code=204)
            response.headers["Access-Control-Allow-Private-Network"] = "true"
            response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-API-Key, Content-Type"
            return response

        response: Response = await call_next(request)
        response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "script-src 'self'; "
            "frame-ancestors 'none'"
        )
        # Cache static assets for 1 day
        path = request.url.path
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple per-IP rate limiting."""
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not rate_limiter.allow(client_ip):
            return Response("Rate limit exceeded", status_code=429)
        return await call_next(request)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log every request with client IP, method, path, and status code."""
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        has_key = bool(
            request.headers.get("X-API-Key") or request.query_params.get("api_key")
        )
        has_session = bool(request.cookies.get("session"))
        auth_method = "key" if has_key else ("session" if has_session else "none")
        audit_logger.info(
            "%s %s %s -> %d (%.0fms, auth=%s)",
            client_ip,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            auth_method,
        )
        return response


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------
def _check_auth(request: Request):
    """Validate session cookie or API key. No-op if auth is not configured."""
    if not _is_auth_required():
        return  # No auth configured — open access

    # 1. Check session cookie
    session_token = request.cookies.get("session")
    if session_token and _verify_session_token(session_token):
        return

    # 2. Check API key
    if API_KEY:
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if key and hmac.compare_digest(key, API_KEY):
            return

    raise HTTPException(status_code=401, detail="Authentication required")


def require_auth(request: Request):
    """FastAPI dependency for protected endpoints."""
    _check_auth(request)


# ---------------------------------------------------------------------------
# Signal handlers for graceful shutdown
# ---------------------------------------------------------------------------
def _handle_shutdown_signal(signum, frame):
    """Save state on SIGTERM / SIGINT before process exits."""
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name} — saving visitor state before exit")
    try:
        detection_engine.body_tracker.save_state()
        logger.info("Visitor state saved successfully on signal")
    except Exception as e:
        logger.error(f"Error saving state on signal: {e}")
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_shutdown_signal)
signal.signal(signal.SIGINT, _handle_shutdown_signal)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting application...")

    # Auto-start monitoring on startup
    try:
        logger.info("Auto-starting CCTV monitoring...")
        cctv_handler.start()
        await stream_manager.start_streaming()
        logger.info("CCTV monitoring started successfully")
    except Exception as e:
        logger.error(f"Failed to auto-start monitoring: {e}")

    async def _face_cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                deleted = stream_manager.face_store.cleanup_expired()
                if deleted:
                    logger.info("Face capture cleanup: deleted %d expired files", deleted)
            except Exception as e:
                logger.error("Face capture cleanup error: %s", e)

    cleanup_task = asyncio.create_task(_face_cleanup_loop())

    async def _person_cleanup_loop():
        while True:
            await asyncio.sleep(3600)
            try:
                deleted = stream_manager.person_store.cleanup_expired()
                if deleted:
                    logger.info("Person capture cleanup: deleted %d expired files", deleted)
            except Exception as e:
                logger.error("Person capture cleanup error: %s", e)

    person_cleanup_task = asyncio.create_task(_person_cleanup_loop())

    yield

    logger.info("Shutting down application...")
    try:
        detection_engine.body_tracker.save_state()
        logger.info("Visitor state saved successfully")
    except Exception as e:
        logger.error(f"Error saving visitor state on shutdown: {e}")

    cleanup_task.cancel()
    person_cleanup_task.cancel()
    try:
        await asyncio.gather(cleanup_task, person_cleanup_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    await stream_manager.stop_streaming()
    cctv_handler.stop()


app = FastAPI(
    title="CCTV Detection System",
    description="Real-time people and gender detection from CCTV streams",
    version="2.0.0",
    lifespan=lifespan
)

# Middleware (order matters — outermost first)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

# Mount static files
static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path), name="frontend")


# ---------------------------------------------------------------------------
# Pydantic models with validation
# ---------------------------------------------------------------------------
class SettingsUpdate(BaseModel):
    confidence: float | None = None
    enable_gender: bool | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v):
        if v is not None and not (0.1 <= v <= 0.95):
            raise ValueError("confidence must be between 0.1 and 0.95")
        return v


class SettingsResponse(BaseModel):
    confidence: float
    enable_gender: bool
    stream_active: bool
    cctv_connected: bool


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
async def root(request: Request):
    """Serve the frontend (requires auth if configured)."""
    if _is_auth_required():
        session_token = request.cookies.get("session")
        if not session_token or not _verify_session_token(session_token):
            return RedirectResponse(url="/login", status_code=302)
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "CCTV Detection System API", "docs": "/docs"}


@app.get("/login")
async def login_page(request: Request):
    """Serve the login page."""
    if not _is_auth_required():
        return RedirectResponse(url="/", status_code=302)
    # If already logged in, redirect to dashboard
    session_token = request.cookies.get("session")
    if session_token and _verify_session_token(session_token):
        return RedirectResponse(url="/", status_code=302)
    login_path = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path)
    return HTMLResponse("<h1>Login page not found</h1>", status_code=500)


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Authenticate and set session cookie."""
    if not _is_auth_required():
        return RedirectResponse(url="/", status_code=302)

    if hmac.compare_digest(username, ADMIN_USERNAME) and hmac.compare_digest(password, ADMIN_PASSWORD):
        token = _create_session_token(username)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key="session",
            value=token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
        )
        logger.info(f"User '{username}' logged in from {request.client.host}")
        return response

    logger.warning(f"Failed login attempt for '{username}' from {request.client.host}")
    login_path = os.path.join(frontend_path, "login.html")
    if os.path.exists(login_path):
        with open(login_path) as _f:
            content = _f.read().replace(
                "<!--ERROR_PLACEHOLDER-->",
                '<div class="login-error">Invalid username or password</div>'
            )
        return HTMLResponse(content, status_code=401)
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/logout")
async def logout():
    """Clear session and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session")
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint with model & component status."""
    detector = detection_engine.person_detector
    return {
        "status": "healthy",
        "cctv_connected": cctv_handler.is_connected,
        "streaming": stream_manager.streaming,
        "uptime_seconds": (datetime.now() - start_time).total_seconds(),
        "models": {
            "yolo_loaded": detector.model_loaded,
            "insightface_loaded": detection_engine.face_analyzer.insightface.model_loaded,
            "osnet_loaded": detection_engine.osnet.available,
            "last_detection": detector.last_detection_time,
        },
        "active_visitors": detection_engine.get_active_visitors(),
        "websocket_clients": stream_manager.connection_manager.connection_count,
    }


@app.get("/settings", response_model=SettingsResponse, dependencies=[Depends(require_auth)])
async def get_settings():
    """Get current settings."""
    return SettingsResponse(
        confidence=detection_engine.person_detector.confidence,
        enable_gender=detection_engine.enable_gender,
        stream_active=stream_manager.streaming,
        cctv_connected=cctv_handler.is_connected
    )


@app.post("/settings", dependencies=[Depends(require_auth)])
async def update_settings(settings: SettingsUpdate):
    """Update detection settings."""
    if settings.confidence is not None:
        detection_engine.set_confidence(settings.confidence)

    if settings.enable_gender is not None:
        detection_engine.set_gender_enabled(settings.enable_gender)

    return {"message": "Settings updated", "settings": await get_settings()}


@app.get("/stats", dependencies=[Depends(require_auth)])
async def get_stats():
    """Get detection statistics."""
    stats = stream_manager.get_stats()
    stats["uptime_seconds"] = (datetime.now() - start_time).total_seconds()

    today_saved = data_storage.get_today_stats()
    stats["today_saved"] = today_saved

    return stats


@app.get("/stats/weekly", dependencies=[Depends(require_auth)])
async def get_weekly_stats():
    """Get weekly statistics."""
    return data_storage.get_weekly_stats()


@app.get("/stats/monthly", dependencies=[Depends(require_auth)])
async def get_monthly_stats():
    """Get monthly statistics."""
    return data_storage.get_monthly_stats()


@app.get("/stats/all-time", dependencies=[Depends(require_auth)])
async def get_all_time_stats():
    """Get all-time statistics."""
    return data_storage.get_all_time_stats()


@app.get("/stats/export", dependencies=[Depends(require_auth)])
async def export_stats():
    """Export all historical statistics as CSV."""
    csv_content = data_storage.export_csv()
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=visitor_stats.csv"}
    )


@app.get("/stats/export/pdf", dependencies=[Depends(require_auth)])
async def export_pdf():
    """Export a comprehensive PDF report of all visitor statistics."""
    today = data_storage.get_today_stats()
    weekly = data_storage.get_weekly_stats()
    monthly = data_storage.get_monthly_stats()
    alltime = data_storage.get_all_time_stats()

    weekly_daily = data_storage.get_daily_range(
        weekly.get("start_date", ""), weekly.get("end_date", "")
    )
    monthly_daily = data_storage.get_daily_range(
        monthly.get("start_date", ""), monthly.get("end_date", "")
    )

    now = datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M:%S")
    filename = f"Visitor_Report_{now.strftime('%Y-%m-%d')}.pdf"

    pdf_bytes = generate_visitor_report(
        today=today,
        weekly=weekly,
        monthly=monthly,
        alltime=alltime,
        weekly_daily=weekly_daily,
        monthly_daily=monthly_daily,
        generated_at=generated_at,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/reset-stats", dependencies=[Depends(require_auth)])
async def reset_stats():
    """Reset session statistics."""
    stream_manager.reset_session_stats()
    data_storage.reset_today()
    return {"message": "Statistics reset"}


@app.post("/stream/start", dependencies=[Depends(require_auth)])
async def start_stream():
    """Start the CCTV stream and detection."""
    try:
        if not cctv_handler.is_running():
            cctv_handler.start()

        await stream_manager.start_streaming()
        return {"message": "Stream started", "status": "running"}
    except Exception as e:
        logger.error(f"Failed to start stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/stream/stop", dependencies=[Depends(require_auth)])
async def stop_stream():
    """Stop the CCTV stream and detection."""
    await stream_manager.stop_streaming()
    cctv_handler.stop()
    return {"message": "Stream stopped", "status": "stopped"}


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """WebSocket endpoint for video streaming."""
    # Validate auth for WebSocket if configured
    if _is_auth_required():
        # Check session cookie first, then API key
        session_token = websocket.cookies.get("session")
        has_session = session_token and _verify_session_token(session_token)
        has_api_key = API_KEY and websocket.query_params.get("api_key") == API_KEY
        if not has_session and not has_api_key:
            await websocket.close(code=4001, reason="Authentication required")
            return

    await stream_manager.connection_manager.connect(websocket)

    # Send current CCTV connection status immediately
    import json
    current_state = cctv_handler.connection_state
    status_message = {
        "type": "status",
        "data": {
            "state": current_state,
            "message": "Camera connected" if current_state == "connected" else "Camera disconnected"
        }
    }
    try:
        await websocket.send_text(json.dumps(status_message))
    except Exception as e:
        logger.error(f"Failed to send initial status: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        stream_manager.connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        stream_manager.connection_manager.disconnect(websocket)


@app.get("/faces", dependencies=[Depends(require_auth)])
async def list_faces():
    """Return the last 20 face captures, newest first."""
    records = stream_manager.face_store.get_recent(limit=20)
    return [{**r, "url": f"/faces/{r['filename']}"} for r in records]


@app.get("/faces/{filename}", dependencies=[Depends(require_auth)])
async def get_face_image(filename: str):
    """Serve a face capture JPEG."""
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+\.jpg", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backend", "data", "face_captures", filename,
    )
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/persons", dependencies=[Depends(require_auth)])
async def list_persons():
    """Return the last 20 person captures, newest first."""
    records = stream_manager.person_store.get_recent(limit=20)
    return [{**r, "url": f"/persons/{r['filename']}"} for r in records]


@app.get("/persons/{filename}", dependencies=[Depends(require_auth)])
async def get_person_image(filename: str):
    """Serve a person body crop JPEG."""
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+\.jpg", filename):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backend", "data", "person_captures", filename,
    )
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/rootCA.pem", include_in_schema=False)
async def download_ca():
    """Serve the mkcert root CA certificate for client installation."""
    ca_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "certs", "rootCA.pem")
    return FileResponse(ca_path, media_type="application/x-pem-file", filename="visitor-analytics-CA.pem")


@app.get("/proxy.pac", include_in_schema=False)
async def proxy_pac():
    """Serve a PAC file that bypasses proxy for this server."""
    pac = """function FindProxyForURL(url, host) {
    if (host === "visitor-analysis.local") return "DIRECT";
    if (isInNet(dnsResolve(host), "10.0.0.0", "255.0.0.0") ||
        isInNet(dnsResolve(host), "172.16.0.0", "255.240.0.0") ||
        isInNet(dnsResolve(host), "192.168.0.0", "255.255.0.0")) return "DIRECT";
    return "USEPROXY";
}"""
    return PlainTextResponse(pac, media_type="application/x-ns-proxy-autoconfig")


@app.get("/detect-all")
async def detect_all_page():
    """Serve the YOLO26 all-classes detection explorer page."""
    page_path = os.path.join(frontend_path, "detect-all.html")
    if os.path.exists(page_path):
        return FileResponse(page_path)
    raise HTTPException(status_code=404, detail="Page not found")


@app.websocket("/ws/detect-all")
async def websocket_detect_all(websocket: WebSocket):
    """Stream CCTV feed with all YOLO26 detections (all 80 classes)."""
    await websocket.accept()
    ping_task = None
    try:
        import base64
        import json as _json_local

        # Reuse the already-loaded model — avoids 10s reload and double VRAM usage
        model = detection_engine.person_detector.model
        loop = asyncio.get_event_loop()

        COLORS = {}
        def get_color(cls_id):
            if cls_id not in COLORS:
                import colorsys
                hue = (cls_id * 37) % 180 / 180.0
                r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.95)
                COLORS[cls_id] = (int(b * 255), int(g * 255), int(r * 255))
            return COLORS[cls_id]

        def process_frame(frame):
            results = model(frame, verbose=False, imgsz=1280, half=True, device=0, conf=0.3)
            detections = []
            annotated = frame.copy()
            for result in results:
                for box in (result.boxes or []):
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    cls_name = model.names.get(cls_id, str(cls_id))
                    color = get_color(cls_id)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    label = f"{cls_name} {conf:.0%}"
                    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
                    cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
                    cv2.putText(annotated, label, (x1 + 2, y1 - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
                    detections.append({"cls": cls_name, "conf": round(conf, 2)})
            _, buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            return base64.b64encode(buf).decode(), detections

        # Handle pings in a background task so the frame loop is never blocked
        disconnected = False

        async def ping_receiver():
            nonlocal disconnected
            try:
                while True:
                    data = await websocket.receive_text()
                    if data == "ping":
                        await websocket.send_text("pong")
            except Exception:
                disconnected = True

        ping_task = asyncio.ensure_future(ping_receiver())

        while not disconnected:
            frame = cctv_handler.get_frame()
            if frame is None:
                await asyncio.sleep(0.04)
                continue

            b64, detections = await loop.run_in_executor(None, process_frame, frame)
            msg = _json_local.dumps({"type": "frame", "data": b64, "detections": detections})
            try:
                await websocket.send_text(msg)
            except Exception:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"detect-all WebSocket error: {e}")
    finally:
        if ping_task and not ping_task.done():
            ping_task.cancel()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
