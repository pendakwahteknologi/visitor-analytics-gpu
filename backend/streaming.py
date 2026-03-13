import cv2
import asyncio
import json
import logging
import os
import threading
from typing import Set, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from config import JPEG_QUALITY, STREAM_FPS, MIN_PERSON_W, MIN_PERSON_H
from face_capture_store import FaceCaptureStore
from person_capture_store import PersonCaptureStore

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

    async def broadcast_bytes(self, data: bytes):
        """Broadcast binary frame to all connected clients."""
        if not self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_bytes(data)
            except Exception as e:
                logger.warning(f"Failed to send frame: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.active_connections.discard(conn)

    async def broadcast_text(self, message: str):
        """Broadcast text message (status, captures) to all connected clients."""
        if not self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send text: {e}")
                disconnected.add(connection)

        for conn in disconnected:
            self.active_connections.discard(conn)

    async def broadcast_status(self, status_data: Dict[str, Any]):
        """Broadcast connection status to all connected clients."""
        message = json.dumps({
            "type": "status",
            "data": status_data
        })
        await self.broadcast_text(message)

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


def encode_frame_to_jpeg(frame, quality: int = JPEG_QUALITY, max_width: int = 1280) -> bytes:
    """Encode a frame to raw JPEG bytes."""
    height, width = frame.shape[:2]
    if width > max_width:
        scale = max_width / width
        new_width = max_width
        new_height = int(height * scale)
        frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)

    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
    _, buffer = cv2.imencode('.jpg', frame, encode_param)
    return buffer.tobytes()


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

        _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.face_store = FaceCaptureStore(
            capture_dir=os.path.join(_project_root, "backend", "data", "face_captures")
        )

        self.person_store = PersonCaptureStore(
            capture_dir=os.path.join(_project_root, "backend", "data", "person_captures")
        )

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
        self._stats_lock = threading.Lock()  # protects current_stats and prev_track_ids
        self.prev_track_ids: set = set()

    async def start_streaming(self):
        """Start the streaming loop."""
        if self.streaming:
            logger.warning("Streaming already running")
            return

        # Register callback for CCTV state changes
        self.cctv_handler.add_state_callback(self._on_cctv_state_change)
        self._event_loop = asyncio.get_running_loop()

        self.streaming = True
        self.stream_task = asyncio.create_task(self._stream_loop())
        logger.info("Streaming started")

    def _on_cctv_state_change(self, state: str, message: str):
        """Callback for CCTV connection state changes."""
        try:
            loop = getattr(self, "_event_loop", None)
            if loop is None:
                return  # not yet started
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
        backoff = 1.0
        max_backoff = 30.0

        while self.streaming:
            try:
                await self._stream_loop_inner()
                backoff = 1.0  # reset on clean exit
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Stream loop crashed — restarting in %.1fs: %s", backoff, e, exc_info=True)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    async def _stream_loop_inner(self):
        """Inner streaming loop — restarted automatically on any unhandled exception."""
        import time

        _loop = asyncio.get_running_loop()  # cache once per loop lifetime

        fps_counter = 0
        fps_timer = time.time()
        frame_counter = 0
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

                is_analysis_frame = frame_counter % analysis_interval == 0

                # ByteTrack: called every frame for consistent tracker state
                # run_in_executor prevents blocking the asyncio event loop
                detections = await _loop.run_in_executor(
                    None, self.detection_engine.person_detector.track, resized_frame
                )

                # Drop detections too small to be a real person (avoids count inflation)
                detections = [
                    det for det in detections
                    if (det.bbox[2] - det.bbox[0]) >= MIN_PERSON_W
                    and (det.bbox[3] - det.bbox[1]) >= MIN_PERSON_H
                ]

                # Carry forward gender/age from previous detection by nearest bbox centre
                if self.detection_engine.enable_gender and last_detections:
                    def _centre(bbox):
                        x1, y1, x2, y2 = bbox
                        return ((x1 + x2) / 2, (y1 + y2) / 2)

                    for det in detections:
                        cx, cy = _centre(det.bbox)
                        best = min(
                            last_detections,
                            key=lambda d: ((_centre(d.bbox)[0] - cx) ** 2 + (_centre(d.bbox)[1] - cy) ** 2)
                        )
                        bx, by = _centre(best.bbox)
                        if ((bx - cx) ** 2 + (by - cy) ** 2) ** 0.5 < 150:
                            det.gender = best.gender
                            det.gender_confidence = best.gender_confidence
                            det.age = best.age
                            det.age_group = best.age_group
                            det.embedding = best.embedding
                            det.visitor_id = best.visitor_id

                last_detections = detections

                # Build set of current track IDs (only from detections that passed the filter)
                current_track_ids = {det.track_id for det in detections if det.track_id is not None}

                # Split detections: unconfirmed need Re-ID, confirmed may still need gender
                confirmed_map = self.detection_engine.body_tracker.track_to_person
                detections_needing_analysis = [
                    det for det in detections
                    if det.track_id is None or det.track_id not in confirmed_map
                ]

                # Confirmed tracks that still have Unknown gender — need face/body gender analysis
                detections_needing_gender = []
                if self.detection_engine.enable_gender and is_analysis_frame:
                    body_tracker = self.detection_engine.body_tracker
                    for det in detections:
                        if det.track_id is not None and det.track_id in confirmed_map:
                            pid = confirmed_map[det.track_id]
                            with body_tracker.lock:
                                person = body_tracker.persons.get(pid)
                                if person and person.get("gender") in (None, "Unknown"):
                                    detections_needing_gender.append((det, pid))

                # Always initialise age_groups for stats
                age_groups = {
                    "Children": 0, "Teens": 0, "Young Adults": 0,
                    "Adults": 0, "Seniors": 0, "Unknown": 0
                }

                # Combine all detections that need face analysis
                all_face_dets = list(detections_needing_analysis)
                gender_only_dets = [det for det, _pid in detections_needing_gender]
                all_face_dets.extend(gender_only_dets)

                # Face analysis (heavy — only on analysis frames, only when gender enabled)
                all_analyses = [{}] * len(all_face_dets)
                if self.detection_engine.enable_gender and is_analysis_frame and all_face_dets:
                    raw_results = await asyncio.gather(*[
                        _loop.run_in_executor(
                            None, self.detection_engine.face_analyzer.analyze,
                            resized_frame, det.bbox
                        )
                        for det in all_face_dets
                    ], return_exceptions=True)
                    all_analyses = [
                        r if not isinstance(r, Exception)
                        else {"gender": None, "gender_confidence": 0.0,
                              "age": None, "age_group": "Unknown", "embedding": None}
                        for r in raw_results
                    ]

                # Split analyses back: first N are for unconfirmed, rest for gender-only
                analyses = all_analyses[:len(detections_needing_analysis)]
                gender_analyses = all_analyses[len(detections_needing_analysis):]

                # Apply face results to unconfirmed detections
                if self.detection_engine.enable_gender and is_analysis_frame:
                    for det, analysis in zip(detections_needing_analysis, analyses):
                        det.gender = analysis["gender"]
                        det.gender_confidence = analysis["gender_confidence"]
                        det.age = analysis["age"]
                        det.age_group = analysis["age_group"]
                        det.embedding = analysis["embedding"]

                        # Save face crop when gender is known
                        if analysis.get("gender") and analysis["gender"] != "Unknown":
                            try:
                                has_embedding = analysis.get("embedding") is not None
                                face_record = self.face_store.save_capture(
                                    resized_frame, det.bbox, analysis,
                                    visitor_id=getattr(det, "visitor_id", None) if has_embedding else None,
                                    is_new_visitor=getattr(det, "is_new_visitor", False) if has_embedding else False,
                                )
                                if face_record:
                                    await self._broadcast_face_capture(face_record)
                            except Exception as e:
                                logger.error("Face capture error: %s", e)

                        if det.age_group and det.age_group != "Unknown":
                            age_groups[det.age_group] += 1
                        else:
                            age_groups["Unknown"] += 1

                # Apply face/body-gender results to confirmed-but-unknown-gender tracks
                if detections_needing_gender and is_analysis_frame:
                    for (det, pid), analysis in zip(detections_needing_gender, gender_analyses):
                        gender = analysis.get("gender") if analysis else None
                        age = analysis.get("age") if analysis else None
                        age_group = analysis.get("age_group") if analysis else None

                        # Body-gender fallback for confirmed tracks too
                        if self.detection_engine.enable_gender and (gender is None or gender == "Unknown"):
                            x1, y1, x2, y2 = det.bbox
                            crop = resized_frame[y1:y2, x1:x2]
                            if crop.size > 0:
                                gender = await _loop.run_in_executor(
                                    None, self.detection_engine.body_gender.predict, crop
                                )

                        if gender and gender != "Unknown":
                            self.detection_engine.body_tracker.attach_gender(
                                pid, gender, age, age_group
                            )

                # Body Re-ID (on analysis frames, only for detections needing analysis)
                if is_analysis_frame:
                    body_embeddings = await asyncio.gather(*[
                        _loop.run_in_executor(
                            None, self.detection_engine.osnet.extract,
                            resized_frame, det.bbox,
                        )
                        for det in detections_needing_analysis
                    ], return_exceptions=True)

                    for det, body_emb, analysis in zip(detections_needing_analysis, body_embeddings, analyses):
                        if isinstance(body_emb, Exception):
                            body_emb = None

                        # Small crops (body_emb is None) are now handled via track_id-only Re-ID

                        gender    = analysis.get("gender") if analysis else None
                        age       = analysis.get("age") if analysis else None
                        age_group = analysis.get("age_group") if analysis else None

                        # Body-gender fallback (only when enable_gender=True and face didn't classify)
                        if self.detection_engine.enable_gender and (gender is None or gender == "Unknown") and body_emb is not None:
                            x1, y1, x2, y2 = det.bbox
                            crop = resized_frame[y1:y2, x1:x2]
                            if crop.size > 0:
                                gender = await _loop.run_in_executor(
                                    None, self.detection_engine.body_gender.predict, crop
                                )

                        is_new, person_id = self.detection_engine.body_tracker.check_person(
                            body_emb,
                            track_id=det.track_id,
                            gender=gender,
                            age=age,
                            age_group=age_group,
                            active_track_ids=current_track_ids,
                        )

                        if person_id is not None:
                            det.visitor_id = person_id
                            det.is_new_visitor = is_new

                        if is_new and person_id is not None:
                            try:
                                person_record = self.person_store.save_capture(
                                    resized_frame, det.bbox,
                                    person_id=person_id,
                                    gender=gender, age=age, age_group=age_group,
                                    is_new=True,
                                )
                                if person_record:
                                    await self._broadcast_person_capture(person_record)
                            except Exception as e:
                                logger.error("Person capture error: %s", e)
                            # Flush new unique person count to DB immediately
                            self._save_stats_now()
                            last_save_time = time.time()

                        elif not is_new and person_id is not None:
                            if gender and gender != "Unknown":
                                self.detection_engine.body_tracker.attach_gender(
                                    person_id, gender, age, age_group
                                )
                            try:
                                person_record = self.person_store.save_capture(
                                    resized_frame, det.bbox,
                                    person_id=person_id,
                                    gender=gender, age=age, age_group=age_group,
                                    is_new=False,
                                )
                                if person_record:
                                    await self._broadcast_person_capture(person_record)
                            except Exception as e:
                                logger.error("Person capture refresh error: %s", e)

                # Evict ByteTrack IDs that disappeared this frame
                with self._stats_lock:
                    gone_ids = self.prev_track_ids - current_track_ids
                    self.prev_track_ids = current_track_ids
                for gone_id in gone_ids:
                    self.detection_engine.body_tracker.clear_track(gone_id)

                # Live stats for display
                stats = {
                    "total_people": len(detections),
                    "male": sum(1 for d in detections if d.gender == "Male"),
                    "female": sum(1 for d in detections if d.gender == "Female"),
                    "unknown": sum(1 for d in detections if d.gender == "Unknown" or d.gender is None),
                    "age_groups": dict(age_groups),  # snapshot to avoid shared ref
                }
                last_stats = stats

                with self._stats_lock:
                    self.current_stats["total_people"] = stats["total_people"]
                    self.current_stats["male"] = stats["male"]
                    self.current_stats["female"] = stats["female"]
                    self.current_stats["unknown"] = stats["unknown"]
                    self.current_stats["age_groups"] = stats["age_groups"]

                # Annotate and broadcast frame (skip work when nobody is watching)
                if self.cctv_handler.connection_state == "connected" and self.connection_manager.connection_count > 0:
                    annotated_frame = self.detection_engine.person_detector.draw_detections(
                        resized_frame, detections
                    )
                    jpeg_bytes = encode_frame_to_jpeg(annotated_frame, quality=70, max_width=1280)
                    await self.connection_manager.broadcast_bytes(jpeg_bytes)

                fps_counter += 1

            # Calculate FPS
            if time.time() - fps_timer >= 1.0:
                with self._stats_lock:
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

    def _save_stats_now(self) -> None:
        """Immediately persist current visitor stats to DB."""
        if not self.data_storage:
            return
        try:
            visitor_stats = self.detection_engine.get_visitor_stats()
            self.data_storage.save_current_stats(
                visitor_stats["total_visitors"],
                visitor_stats["male"],
                visitor_stats["female"],
                visitor_stats["age_groups"],
                visitor_stats.get("unknown", 0),
            )
        except Exception as e:
            logger.error("Immediate DB save failed: %s", e)

    def get_stats(self) -> dict:
        """Get current frame stats and visitor statistics."""
        visitor_stats = self.detection_engine.get_visitor_stats()
        with self._stats_lock:
            current_snapshot = {
                "total_people": self.current_stats["total_people"],
                "male": self.current_stats["male"],
                "female": self.current_stats["female"],
                "unknown": self.current_stats["unknown"],
                "fps": self.current_stats["fps"],
                "age_groups": dict(self.current_stats["age_groups"]),
            }
        return {
            "current": current_snapshot,
            "session": {
                "total_detected": visitor_stats["total_visitors"],
                "male_detected": visitor_stats["male"],
                "female_detected": visitor_stats["female"],
                "age_groups": visitor_stats["age_groups"]
            },
            "connections": self.connection_manager.connection_count,
            "active_visitors": self.detection_engine.get_active_visitors()
        }

    async def _broadcast_face_capture(self, record: dict) -> None:
        """Broadcast a face_capture event to all connected WebSocket clients."""
        message = json.dumps({
            "type": "face_capture",
            "data": {
                "id": record["id"],
                "url": f"/faces/{record['filename']}",
                "timestamp": record["timestamp"],
                "gender": record["gender"],
                "age": record["age"],
                "age_group": record["age_group"],
                "visitor_id": record["visitor_id"],
                "is_new_visitor": record["is_new_visitor"],
            }
        })
        await self.connection_manager.broadcast_text(message)

    async def _broadcast_person_capture(self, record: dict) -> None:
        """Broadcast a person_capture event to all connected WebSocket clients."""
        message = json.dumps({
            "type": "person_capture",
            "data": {
                "id": record["id"],
                "url": f"/persons/{record['filename']}",
                "timestamp": record["timestamp"],
                "gender": record["gender"],
                "age": record["age"],
                "age_group": record["age_group"],
                "person_id": record["person_id"],
                "is_new": record["is_new"],
            }
        })
        await self.connection_manager.broadcast_text(message)

    def reset_session_stats(self):
        """Reset visitor tracking statistics."""
        self.detection_engine.reset_visitor_stats()
        logger.info("Session stats reset")
