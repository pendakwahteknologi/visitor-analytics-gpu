import cv2
import asyncio
import base64
import json
import logging
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from config import JPEG_QUALITY, STREAM_FPS

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections for streaming."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"Client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast_frame(self, frame_data: str):
        """Broadcast frame to all connected clients."""
        if not self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(frame_data)
            except Exception as e:
                logger.warning(f"Failed to send frame: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)

    async def broadcast_status(self, status_data: Dict[str, Any]):
        """Broadcast connection status to all connected clients."""
        if not self.active_connections:
            return

        message = json.dumps({
            "type": "status",
            "data": status_data
        })

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send status: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            self.active_connections.discard(conn)

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


def encode_frame_to_base64(frame, quality: int = JPEG_QUALITY, max_width: int = 1280) -> str:
    """Encode a frame to base64 JPEG string with JSON envelope."""
    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / width
        new_width = max_width
        new_height = int(height * scale)
        frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, buffer = cv2.imencode('.jpg', frame, encode_param)
    base64_frame = base64.b64encode(buffer).decode('utf-8')

    return json.dumps({
        "type": "frame",
        "data": base64_frame
    })


class StreamManager:
    """Manage video streaming with detection and visitor tracking."""

    def __init__(self, cctv_handler, detection_engine, data_storage=None):
        self.cctv_handler = cctv_handler
        self.detection_engine = detection_engine
        self.data_storage = data_storage
        self.connection_manager = ConnectionManager()
        self.streaming = False
        self.stream_task = None
        self.frame_interval = 1.0 / STREAM_FPS

        # Current frame stats (for live display)
        self.current_stats = {
            "total_people": 0,
            "male": 0,
            "female": 0,
            "unknown": 0,
            "fps": 0,
            "age_groups": {
                "Children": 0,
                "Teens": 0,
                "Young Adults": 0,
                "Adults": 0,
                "Seniors": 0,
                "Unknown": 0
            }
        }

    async def start_streaming(self):
        """Start the streaming loop."""
        if self.streaming:
            logger.warning("Streaming already running")
            return

        # Register callback for CCTV state changes
        self.cctv_handler.add_state_callback(self._on_cctv_state_change)
        self._event_loop = asyncio.get_event_loop()

        self.streaming = True
        self.stream_task = asyncio.create_task(self._stream_loop())
        logger.info("Streaming started")

    def _on_cctv_state_change(self, state: str, message: str):
        """Callback for CCTV connection state changes."""
        try:
            loop = getattr(self, "_event_loop", None) or asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.connection_manager.broadcast_status({
                        "state": state,
                        "message": message
                    }),
                    loop
                )
        except Exception as e:
            logger.error(f"Error broadcasting CCTV state change: {e}")

    async def stop_streaming(self):
        """Stop the streaming loop."""
        self.streaming = False
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
            self.stream_task = None
        logger.info("Streaming stopped")

    async def _stream_loop(self):
        """Main streaming loop with optimized detection and visitor tracking."""
        import time

        fps_counter = 0
        fps_timer = time.time()
        frame_counter = 0
        detection_interval = 2  # Run person detection every 2 frames (yolov8x+imgsz1280 is heavy)
        analysis_interval = 4  # Run face analysis every 4 frames
        last_detections = []
        last_stats = {
            "total_people": 0, "male": 0, "female": 0, "unknown": 0,
            "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0, "Adults": 0, "Seniors": 0, "Unknown": 0}
        }
        save_interval = 30  # Save to file every 30 seconds
        last_save_time = time.time()

        while self.streaming:
            loop_start = time.time()

            # Get frame from CCTV
            frame = self.cctv_handler.get_frame()

            if frame is not None:
                frame_counter += 1

                # Resize frame for faster processing
                height, width = frame.shape[:2]
                if width > 1280:
                    scale = 1280 / width
                    new_width = 1280
                    new_height = int(height * scale)
                    resized_frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
                else:
                    resized_frame = frame

                # Run detection with optimized intervals
                is_detection_frame = frame_counter % detection_interval == 0
                is_analysis_frame = frame_counter % analysis_interval == 0

                if is_detection_frame:
                    # Run person detection
                    detections = self.detection_engine.person_detector.detect(resized_frame)
                    last_detections = detections

                    # Initialize age group stats for current frame
                    age_groups = {"Children": 0, "Teens": 0, "Young Adults": 0, "Adults": 0, "Seniors": 0, "Unknown": 0}

                    # Only run face analysis on fresh detection frames
                    if self.detection_engine.enable_gender and is_analysis_frame:
                        loop = asyncio.get_event_loop()
                        raw_results = await asyncio.gather(*[
                            loop.run_in_executor(None, self.detection_engine.face_analyzer.analyze, resized_frame, det.bbox)
                            for det in detections
                        ], return_exceptions=True)
                        analyses = [
                            r if not isinstance(r, Exception) else {"gender": None, "gender_confidence": 0.0, "age": None, "age_group": "Unknown", "embedding": None}
                            for r in raw_results
                        ]
                        for det, analysis in zip(detections, analyses):
                            det.gender = analysis["gender"]
                            det.gender_confidence = analysis["gender_confidence"]
                            det.age = analysis["age"]
                            det.age_group = analysis["age_group"]
                            det.embedding = analysis["embedding"]

                            # Check if this is a new visitor (re-identification)
                            if analysis["embedding"] is not None:
                                is_new, visitor_id = self.detection_engine.visitor_tracker.check_visitor(
                                    analysis["embedding"],
                                    analysis["gender"],
                                    analysis["age_group"],
                                    age=analysis["age"],
                                )
                                det.is_new_visitor = is_new
                                det.visitor_id = visitor_id

                            # Count age groups for current frame display
                            if det.age_group and det.age_group != "Unknown":
                                age_groups[det.age_group] += 1
                            else:
                                age_groups["Unknown"] += 1

                    # Calculate stats for current frame display
                    stats = {
                        "total_people": len(detections),
                        "male": sum(1 for d in detections if d.gender == "Male"),
                        "female": sum(1 for d in detections if d.gender == "Female"),
                        "unknown": sum(1 for d in detections if d.gender == "Unknown" or d.gender is None),
                        "age_groups": age_groups
                    }
                    last_stats = stats

                    # Update current stats (for live display)
                    self.current_stats["total_people"] = stats["total_people"]
                    self.current_stats["male"] = stats["male"]
                    self.current_stats["female"] = stats["female"]
                    self.current_stats["unknown"] = stats["unknown"]
                    self.current_stats["age_groups"] = stats["age_groups"]

                    # Draw detections
                    annotated_frame = self.detection_engine.person_detector.draw_detections(
                        resized_frame, detections
                    )
                else:
                    # Reuse last detection results for intermediate frames
                    annotated_frame = self.detection_engine.person_detector.draw_detections(
                        resized_frame, last_detections
                    )

                # Only broadcast frames if CCTV is connected
                if self.cctv_handler.connection_state == "connected":
                    frame_data = encode_frame_to_base64(annotated_frame, quality=70, max_width=1280)
                    await self.connection_manager.broadcast_frame(frame_data)

                fps_counter += 1

            # Calculate FPS
            if time.time() - fps_timer >= 1.0:
                self.current_stats["fps"] = fps_counter
                fps_counter = 0
                fps_timer = time.time()

            # Save data periodically
            if self.data_storage and time.time() - last_save_time >= save_interval:
                try:
                    visitor_stats = self.detection_engine.get_visitor_stats()
                    self.data_storage.save_current_stats(
                        visitor_stats["total_visitors"],
                        visitor_stats["male"],
                        visitor_stats["female"],
                        visitor_stats["age_groups"],
                        visitor_stats.get("unknown", 0)
                    )
                    last_save_time = time.time()
                except Exception as e:
                    logger.error(f"Failed to save stats: {e}")

            # Frame rate control
            elapsed = time.time() - loop_start
            if elapsed < self.frame_interval:
                await asyncio.sleep(self.frame_interval - elapsed)

    def get_stats(self) -> dict:
        """Get current frame stats and visitor statistics."""
        visitor_stats = self.detection_engine.get_visitor_stats()
        return {
            "current": self.current_stats.copy(),
            "session": {
                "total_detected": visitor_stats["total_visitors"],
                "male_detected": visitor_stats["male"],
                "female_detected": visitor_stats["female"],
                "age_groups": visitor_stats["age_groups"]
            },
            "connections": self.connection_manager.connection_count,
            "active_visitors": self.detection_engine.get_active_visitors()
        }

    def reset_session_stats(self):
        """Reset visitor tracking statistics."""
        self.detection_engine.reset_visitor_stats()
        logger.info("Session stats reset")
