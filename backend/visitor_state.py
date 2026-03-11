"""Visitor state persistence to survive system reboots and power loss.

Supports optional at-rest encryption for face embeddings via EMBEDDING_ENCRYPTION_KEY.
"""

import numpy as np
import logging
import base64
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from .atomic_write import atomic_write_json, atomic_read_json
except ImportError:
    from atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)

# Lazy-loaded encryption
_fernet: Optional[object] = None
_encryption_available = False


def _get_fernet():
    """Lazily initialize Fernet cipher from env key."""
    global _fernet, _encryption_available
    if _fernet is not None:
        return _fernet

    try:
        from config import EMBEDDING_ENCRYPTION_KEY
        if EMBEDDING_ENCRYPTION_KEY:
            from cryptography.fernet import Fernet
            _fernet = Fernet(EMBEDDING_ENCRYPTION_KEY.encode() if isinstance(EMBEDDING_ENCRYPTION_KEY, str) else EMBEDDING_ENCRYPTION_KEY)
            _encryption_available = True
            logger.info("Embedding encryption enabled")
        else:
            _encryption_available = False
    except Exception as e:
        logger.warning(f"Embedding encryption not available: {e}")
        _encryption_available = False

    return _fernet


def _encrypt_embedding(emb_list: list) -> dict:
    """Encrypt an embedding list. Returns tagged dict for deserialization."""
    fernet = _get_fernet()
    if fernet and _encryption_available:
        raw = base64.b64encode(np.array(emb_list, dtype=np.float32).tobytes()).decode()
        encrypted = fernet.encrypt(raw.encode()).decode()
        return {"__encrypted__": True, "data": encrypted}
    return emb_list  # Store as plain list


def _decrypt_embedding(value) -> list:
    """Decrypt an embedding if encrypted, otherwise return as-is."""
    if isinstance(value, dict) and value.get("__encrypted__"):
        fernet = _get_fernet()
        if fernet:
            raw = fernet.decrypt(value["data"].encode()).decode()
            arr = np.frombuffer(base64.b64decode(raw), dtype=np.float32)
            return arr.tolist()
        else:
            logger.warning("Encrypted embedding found but no decryption key available")
            return []
    return value


class VisitorStatePersistence:
    """Handle saving and restoring visitor tracking state."""

    def __init__(self, data_dir: str = "backend/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "visitor_state.json"

    def save_state(
        self,
        persons: Dict,
        pending: Dict,
        stats: Dict,
        next_person_id: int,
    ) -> None:
        """Save BodyReIDTracker state to disk."""
        try:
            state = {
                "persons": self._serialize_visitors(persons),
                "pending": self._serialize_visitors(pending),
                "stats": stats,
                "next_person_id": next_person_id,
            }
            atomic_write_json(self.state_file, state)
            logger.debug(
                "Saved body tracker state: %d confirmed, %d total",
                len(persons), stats["total_visitors"],
            )
        except Exception as e:
            logger.error("Error saving body tracker state: %s", e)

    def restore_state(self) -> tuple:
        """Load BodyReIDTracker state from disk.

        Returns:
            (persons, pending, stats, next_person_id)
        """
        default_stats = {
            "total_visitors": 0, "male": 0, "female": 0, "unknown": 0,
            "age_groups": {
                "Children": 0, "Teens": 0, "Young Adults": 0,
                "Adults": 0, "Seniors": 0, "Unknown": 0,
            },
        }
        try:
            state = atomic_read_json(self.state_file, default={})
            if not state or "persons" not in state:
                return {}, {}, default_stats, 1

            persons = {
                int(k): v
                for k, v in self._deserialize_visitors(state.get("persons", {})).items()
            }
            # pending keys are UUID hex strings — keep as str, not int
            pending = dict(self._deserialize_visitors(state.get("pending", {})))
            stats = state.get("stats", default_stats)
            next_person_id = state.get("next_person_id", 1)

            # Ensure all age_group keys present
            for key in default_stats["age_groups"]:
                stats["age_groups"].setdefault(key, 0)

            logger.info(
                "Restored body tracker: %d confirmed, %d total",
                len(persons), stats["total_visitors"],
            )
            return persons, pending, stats, next_person_id
        except Exception as e:
            logger.error("Error restoring body tracker state: %s", e)
            return {}, {}, default_stats, 1

    def load_state(self) -> Dict[str, Any]:
        """Load visitor tracking state from disk."""
        default_state = {
            "visitors": {},
            "pending_visitors": {},
            "stats": {
                "total_visitors": 0,
                "male": 0,
                "female": 0,
                "unknown": 0,
                "age_groups": {
                    "Children": 0,
                    "Teens": 0,
                    "Young Adults": 0,
                    "Adults": 0,
                    "Seniors": 0,
                    "Unknown": 0
                }
            },
            "next_visitor_id": 1,
            "next_pending_id": 1
        }

        try:
            state = atomic_read_json(self.state_file, default=default_state)

            if "visitors" in state:
                state["visitors"] = self._deserialize_visitors(state["visitors"])

            if "pending_visitors" in state:
                state["pending_visitors"] = self._deserialize_visitors(state["pending_visitors"])

            # Ensure all required fields exist
            for key, value in default_state.items():
                if key not in state:
                    state[key] = value

            # Backward compatibility
            if "stats" in state:
                if "unknown" not in state["stats"]:
                    state["stats"]["unknown"] = 0
                if "age_groups" in state["stats"]:
                    if "Unknown" not in state["stats"]["age_groups"]:
                        state["stats"]["age_groups"]["Unknown"] = 0

            logger.info(
                f"Loaded visitor state: {len(state['visitors'])} confirmed, "
                f"{len(state['pending_visitors'])} pending, "
                f"{state['stats']['total_visitors']} total visitors"
            )

            return state

        except Exception as e:
            logger.error(f"Error loading visitor state: {e}")
            return default_state

    def _serialize_visitors(self, visitors: Dict) -> Dict:
        """Convert visitor dict with numpy arrays to JSON-serializable format."""
        serialized = {}

        for visitor_id, visitor_data in visitors.items():
            serialized_data = visitor_data.copy()

            # Convert numpy embeddings to lists (optionally encrypted)
            if "embeddings" in serialized_data:
                serialized_data["embeddings"] = [
                    _encrypt_embedding(emb.tolist() if isinstance(emb, np.ndarray) else emb)
                    for emb in serialized_data["embeddings"]
                ]

            serialized[visitor_id] = serialized_data

        return serialized

    def _deserialize_visitors(self, visitors: Dict) -> Dict:
        """Convert visitor dict from JSON format back to numpy arrays."""
        deserialized = {}

        for visitor_id, visitor_data in visitors.items():
            deserialized_data = visitor_data.copy()

            # Convert embedding lists/encrypted blobs back to numpy arrays
            if "embeddings" in deserialized_data:
                deserialized_data["embeddings"] = [
                    np.array(_decrypt_embedding(emb)) if not isinstance(emb, np.ndarray) else emb
                    for emb in deserialized_data["embeddings"]
                ]

            deserialized[visitor_id] = deserialized_data

        return deserialized
