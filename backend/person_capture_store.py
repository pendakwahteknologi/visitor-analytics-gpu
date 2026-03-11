"""Person capture storage: save body crops to disk, manage 24h index, throttle duplicates."""

import cv2
import json
import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85
THROTTLE_SECONDS = 30
MIN_CROP_SIZE = 32  # px minimum dimension


class PersonCaptureStore:
    """Save body crop images to disk and maintain a 24-hour rolling index."""

    def __init__(self, capture_dir: str):
        self.capture_dir = capture_dir
        os.makedirs(capture_dir, exist_ok=True)
        self._index_path = os.path.join(capture_dir, "index.json")
        self._last_capture_time: Dict[int, float] = {}  # keyed by person_id

    def save_capture(
        self,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        person_id: int,
        gender: Optional[str],
        age: Optional[int],
        age_group: Optional[str],
        is_new: bool,
    ) -> Optional[dict]:
        """Crop body, save to disk and index. Returns metadata record or None."""
        now = time.time()
        if now - self._last_capture_time.get(person_id, 0) < THROTTLE_SECONDS:
            return None

        crop = self._crop_frame(frame, bbox)
        if crop is None:
            return None

        capture_id = f"{int(now * 1000)}_{uuid.uuid4().hex[:4]}"
        filename = f"{capture_id}.jpg"
        filepath = os.path.join(self.capture_dir, filename)

        ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            logger.warning("Failed to encode body crop %s", capture_id)
            return None

        tmp_filepath = filepath + ".tmp"
        with open(tmp_filepath, "wb") as f:
            f.write(buf.tobytes())
        os.replace(tmp_filepath, filepath)
        self._last_capture_time[person_id] = now

        record = {
            "id": capture_id,
            "filename": filename,
            "timestamp": now,
            "gender": gender,
            "age": age,
            "age_group": age_group or "Unknown",
            "person_id": person_id,
            "is_new": is_new,
        }
        self._append_index(record)
        return record

    def get_recent(self, limit: int = 20) -> List[dict]:
        """Return up to `limit` records, newest first."""
        index = self._load_index()
        index.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return index[:limit]

    def cleanup_expired(self, max_age_seconds: float = 86400) -> int:
        """Delete files and index entries older than max_age_seconds. Returns count deleted."""
        now = time.time()
        index = self._load_index()
        kept, deleted_count = [], 0

        for record in index:
            if now - record.get("timestamp", 0) >= max_age_seconds:
                try:
                    safe_filename = os.path.basename(record["filename"])
                    os.remove(os.path.join(self.capture_dir, safe_filename))
                except FileNotFoundError:
                    pass
                deleted_count += 1
            else:
                kept.append(record)

        if deleted_count:
            self._write_index(kept)

        return deleted_count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _crop_frame(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if (x2 - x1) < MIN_CROP_SIZE or (y2 - y1) < MIN_CROP_SIZE:
            return None
        return frame[y1:y2, x1:x2]

    def _load_index(self) -> List[dict]:
        try:
            with open(self._index_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _append_index(self, record: dict) -> None:
        index = self._load_index()
        index.append(record)
        self._write_index(index)

    def _write_index(self, index: List[dict]) -> None:
        tmp = self._index_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(index, f)
        os.replace(tmp, self._index_path)
