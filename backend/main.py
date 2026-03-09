import os
import sys
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import HOST, PORT, DEBUG, CONFIDENCE_THRESHOLD, GENDER_THRESHOLD, GENDER_ENABLED
from cctv_handler import CCTVHandler
from detection import DetectionEngine
from streaming import StreamManager
from data_storage import DataStorage

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instances
cctv_handler = CCTVHandler()
detection_engine = DetectionEngine(gender_threshold=GENDER_THRESHOLD)
detection_engine.set_gender_enabled(GENDER_ENABLED)
data_storage = DataStorage()
stream_manager = StreamManager(cctv_handler, detection_engine, data_storage)

# Track start time
start_time = datetime.now()


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

    yield

    logger.info("Shutting down application...")
    # Save visitor state before shutdown
    try:
        detection_engine.visitor_tracker.save_state()
        logger.info("Visitor state saved successfully")
    except Exception as e:
        logger.error(f"Error saving visitor state on shutdown: {e}")

    await stream_manager.stop_streaming()
    cctv_handler.stop()


app = FastAPI(
    title="CCTV Detection System",
    description="Real-time people and gender detection from CCTV streams",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
static_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

if os.path.exists(frontend_path):
    app.mount("/frontend", StaticFiles(directory=frontend_path), name="frontend")


# Pydantic models
class SettingsUpdate(BaseModel):
    confidence: float | None = None
    enable_gender: bool | None = None


class SettingsResponse(BaseModel):
    confidence: float
    enable_gender: bool
    stream_active: bool
    cctv_connected: bool


# API Endpoints

@app.get("/")
async def root():
    """Serve the frontend."""
    index_path = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "CCTV Detection System API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "cctv_connected": cctv_handler.is_connected,
        "streaming": stream_manager.streaming,
        "uptime_seconds": (datetime.now() - start_time).total_seconds()
    }


@app.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """Get current settings."""
    return SettingsResponse(
        confidence=detection_engine.person_detector.confidence,
        enable_gender=detection_engine.enable_gender,
        stream_active=stream_manager.streaming,
        cctv_connected=cctv_handler.is_connected
    )


@app.post("/settings")
async def update_settings(settings: SettingsUpdate):
    """Update detection settings."""
    if settings.confidence is not None:
        detection_engine.set_confidence(settings.confidence)

    if settings.enable_gender is not None:
        detection_engine.set_gender_enabled(settings.enable_gender)

    return {"message": "Settings updated", "settings": await get_settings()}


@app.get("/stats")
async def get_stats():
    """Get detection statistics."""
    stats = stream_manager.get_stats()
    stats["uptime_seconds"] = (datetime.now() - start_time).total_seconds()

    # Add today's saved stats
    today_saved = data_storage.get_today_stats()
    stats["today_saved"] = today_saved

    return stats


@app.get("/stats/weekly")
async def get_weekly_stats():
    """Get weekly statistics."""
    return data_storage.get_weekly_stats()


@app.get("/stats/monthly")
async def get_monthly_stats():
    """Get monthly statistics."""
    return data_storage.get_monthly_stats()


@app.get("/stats/all-time")
async def get_all_time_stats():
    """Get all-time statistics."""
    return data_storage.get_all_time_stats()


@app.post("/reset-stats")
async def reset_stats():
    """Reset session statistics."""
    stream_manager.reset_session_stats()
    data_storage.reset_today()
    return {"message": "Statistics reset"}


@app.post("/stream/start")
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


@app.post("/stream/stop")
async def stop_stream():
    """Stop the CCTV stream and detection."""
    await stream_manager.stop_streaming()
    cctv_handler.stop()
    return {"message": "Stream stopped", "status": "stopped"}


@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """WebSocket endpoint for video streaming."""
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
            # Keep connection alive and handle any incoming messages
            data = await websocket.receive_text()
            # Can handle commands from client here if needed
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        stream_manager.connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        stream_manager.connection_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
