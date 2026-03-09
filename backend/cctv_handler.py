import cv2
import threading
import time
from typing import Optional
import logging

from config import CAMERA_RTSP_URL, STREAM_FPS

logger = logging.getLogger(__name__)


class CCTVHandler:
    def __init__(self, rtsp_url: str = CAMERA_RTSP_URL):
        self.rtsp_url = rtsp_url
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame: Optional[cv2.Mat] = None
        self.lock = threading.Lock()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.reconnect_delay_base = 5  # Base delay for exponential backoff
        self.reconnect_delay_max = 60  # Maximum delay between reconnection attempts
        self.frame_interval = 1.0 / STREAM_FPS
        self.connection_state = "disconnected"  # "disconnected", "connecting", "connected"
        self.state_callbacks = []  # List of callbacks for state changes

    def add_state_callback(self, callback):
        """Register a callback to be notified of connection state changes.

        Callback signature: callback(state: str, message: str)
        """
        self.state_callbacks.append(callback)

    def _notify_state_change(self, state: str, message: str):
        """Notify all registered callbacks of a state change."""
        self.connection_state = state
        for callback in self.state_callbacks:
            try:
                callback(state, message)
            except Exception as e:
                logger.error(f"Error in state callback: {e}")

    def _calculate_reconnect_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with cap.

        Formula: min(base * 2^attempt, max)
        """
        delay = self.reconnect_delay_base * (2 ** attempt)
        return min(delay, self.reconnect_delay_max)

    def connect(self) -> bool:
        """Connect to the CCTV stream."""
        try:
            self._notify_state_change("connecting", "Connecting to camera...")

            self.cap = cv2.VideoCapture(self.rtsp_url)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not self.cap.isOpened():
                logger.error(f"Failed to connect to CCTV at {self.rtsp_url}")
                self._notify_state_change("disconnected", "Failed to connect to camera")
                return False

            logger.info(f"Connected to CCTV at {self.rtsp_url}")
            self._notify_state_change("connected", "Camera connected")
            return True
        except Exception as e:
            logger.error(f"Error connecting to CCTV: {e}")
            self._notify_state_change("disconnected", f"Connection error: {e}")
            return False

    def disconnect(self):
        """Disconnect from the CCTV stream."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        logger.info("Disconnected from CCTV")
        if self.connection_state != "disconnected":
            self._notify_state_change("disconnected", "Camera disconnected")

    def _capture_loop(self):
        """Internal loop for capturing frames with infinite reconnection."""
        reconnect_attempt = 0
        last_frame_time = 0

        while self.running:
            current_time = time.time()

            # Handle disconnected state - infinite retry with exponential backoff
            if self.cap is None or not self.cap.isOpened():
                delay = self._calculate_reconnect_delay(reconnect_attempt)
                self._notify_state_change(
                    "reconnecting",
                    f"Attempting to reconnect... (attempt {reconnect_attempt + 1}, waiting {delay}s)"
                )
                logger.warning(
                    f"Attempting to reconnect to CCTV (attempt {reconnect_attempt + 1}, "
                    f"delay: {delay}s)"
                )

                time.sleep(delay)

                if self.connect():
                    logger.info("Reconnected to CCTV successfully")
                    reconnect_attempt = 0  # Reset counter on successful connection
                else:
                    reconnect_attempt += 1  # Increment for next attempt
                continue

            # Frame rate control
            elapsed = current_time - last_frame_time
            if elapsed < self.frame_interval:
                time.sleep(self.frame_interval - elapsed)

            # Try to read frame
            ret, frame = self.cap.read()

            if not ret:
                logger.warning("Failed to read frame from CCTV")
                self.disconnect()
                reconnect_attempt = 0  # Start fresh reconnection sequence
                continue

            # Successfully read frame
            with self.lock:
                self.frame = frame

            last_frame_time = time.time()
            reconnect_attempt = 0  # Reset on successful frame read

    def start(self):
        """Start capturing frames in a background thread."""
        if self.running:
            logger.warning("Capture already running")
            return

        if not self.connect():
            raise ConnectionError("Failed to connect to CCTV")

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info("CCTV capture started")

    def stop(self):
        """Stop capturing frames."""
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=5)
            self.thread = None
        self.disconnect()
        logger.info("CCTV capture stopped")

    def get_frame(self) -> Optional[cv2.Mat]:
        """Get the latest captured frame."""
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
            return None

    def is_running(self) -> bool:
        """Check if capture is running."""
        return self.running

    @property
    def is_connected(self) -> bool:
        """Check if connected to CCTV."""
        return self.cap is not None and self.cap.isOpened()
