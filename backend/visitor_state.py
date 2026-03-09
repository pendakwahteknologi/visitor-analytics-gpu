"""Visitor state persistence to survive system reboots and power loss."""

import numpy as np
import logging
from pathlib import Path
from typing import Dict, Any

try:
    from .atomic_write import atomic_write_json, atomic_read_json
except ImportError:
    from atomic_write import atomic_write_json, atomic_read_json

logger = logging.getLogger(__name__)


class VisitorStatePersistence:
    """Handle saving and restoring visitor tracking state."""

    def __init__(self, data_dir: str = "backend/data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "visitor_state.json"

    def save_state(
        self,
        visitors: Dict,
        pending_visitors: Dict,
        stats: Dict,
        next_visitor_id: int,
        next_pending_id: int
    ) -> None:
        """
        Save visitor tracking state to disk.

        Args:
            visitors: Confirmed visitors dict with embeddings
            pending_visitors: Pending visitors dict
            stats: Current visitor statistics
            next_visitor_id: Next ID to assign
            next_pending_id: Next pending ID to assign
        """
        try:
            # Serialize state, converting numpy arrays to lists
            state = {
                "visitors": self._serialize_visitors(visitors),
                "pending_visitors": self._serialize_visitors(pending_visitors),
                "stats": stats,
                "next_visitor_id": next_visitor_id,
                "next_pending_id": next_pending_id
            }

            atomic_write_json(self.state_file, state)
            logger.debug(
                f"Saved visitor state: {len(visitors)} confirmed, "
                f"{len(pending_visitors)} pending, "
                f"{stats['total_visitors']} total visitors"
            )

        except Exception as e:
            logger.error(f"Error saving visitor state: {e}")

    def load_state(self) -> Dict[str, Any]:
        """
        Load visitor tracking state from disk.

        Returns:
            Dictionary containing:
            - visitors: Confirmed visitors (with numpy embeddings restored)
            - pending_visitors: Pending visitors
            - stats: Visitor statistics
            - next_visitor_id: Next ID to assign
            - next_pending_id: Next pending ID to assign
        """
        default_state = {
            "visitors": {},
            "pending_visitors": {},
            "stats": {
                "total_visitors": 0,
                "male": 0,
                "female": 0,
                "unknown": 0,  # Track unknown gender (deduplicated via face embedding)
                "age_groups": {
                    "Children": 0,
                    "Teens": 0,
                    "Young Adults": 0,
                    "Adults": 0,
                    "Seniors": 0,
                    "Unknown": 0  # Track unknown age groups
                }
            },
            "next_visitor_id": 1,
            "next_pending_id": 1
        }

        try:
            state = atomic_read_json(self.state_file, default=default_state)

            # Deserialize visitors, converting lists back to numpy arrays
            if "visitors" in state:
                state["visitors"] = self._deserialize_visitors(state["visitors"])

            if "pending_visitors" in state:
                state["pending_visitors"] = self._deserialize_visitors(state["pending_visitors"])

            # Ensure all required fields exist
            for key, value in default_state.items():
                if key not in state:
                    state[key] = value

            # Ensure stats has all required fields (for backward compatibility)
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
        """
        Convert visitor dict with numpy arrays to JSON-serializable format.

        Converts numpy arrays to lists for JSON serialization.
        """
        serialized = {}

        for visitor_id, visitor_data in visitors.items():
            serialized_data = visitor_data.copy()

            # Convert numpy embeddings to lists
            if "embeddings" in serialized_data:
                serialized_data["embeddings"] = [
                    emb.tolist() if isinstance(emb, np.ndarray) else emb
                    for emb in serialized_data["embeddings"]
                ]

            serialized[visitor_id] = serialized_data

        return serialized

    def _deserialize_visitors(self, visitors: Dict) -> Dict:
        """
        Convert visitor dict from JSON format back to numpy arrays.

        Converts embedding lists back to numpy arrays.
        """
        deserialized = {}

        for visitor_id, visitor_data in visitors.items():
            deserialized_data = visitor_data.copy()

            # Convert embedding lists back to numpy arrays
            if "embeddings" in deserialized_data:
                deserialized_data["embeddings"] = [
                    np.array(emb) if isinstance(emb, list) else emb
                    for emb in deserialized_data["embeddings"]
                ]

            deserialized[visitor_id] = deserialized_data

        return deserialized
