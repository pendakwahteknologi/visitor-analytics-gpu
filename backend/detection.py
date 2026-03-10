import cv2
import numpy as np
import threading
from ultralytics import YOLO
from typing import List, Dict, Tuple, Optional
import logging
from dataclasses import dataclass, field
import time
from collections import deque
from statistics import median

from config import YOLO_MODEL, CONFIDENCE_THRESHOLD

try:
    from .visitor_state import VisitorStatePersistence
except ImportError:
    from visitor_state import VisitorStatePersistence

logger = logging.getLogger(__name__)

MIN_FACE_SIZE = 40  # Minimum face dimension in pixels


@dataclass
class Detection:
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    gender: Optional[str] = None
    gender_confidence: float = 0.0
    age: Optional[int] = None
    age_group: Optional[str] = None
    embedding: Optional[np.ndarray] = field(default=None, repr=False)
    is_new_visitor: bool = False
    visitor_id: Optional[int] = None


def get_age_group(age: int) -> str:
    """Categorize age into groups."""
    if age <= 12:
        return "Children"
    elif age <= 17:
        return "Teens"
    elif age <= 30:
        return "Young Adults"
    elif age <= 50:
        return "Adults"
    else:
        return "Seniors"


class PersonDetector:
    def __init__(self, model_path: str = YOLO_MODEL, confidence: float = CONFIDENCE_THRESHOLD):
        self.model_path = model_path
        self.confidence = confidence
        self.model: Optional[YOLO] = None
        self.model_loaded = False
        self.last_detection_time: Optional[float] = None
        self._load_model()

    def _load_model(self):
        """Load the YOLO model."""
        try:
            self.model = YOLO(self.model_path)
            self.model_loaded = True
            logger.info(f"Loaded YOLO model: {self.model_path}")
        except (FileNotFoundError, OSError) as e:
            logger.error(f"Failed to load YOLO model file: {e}")
            raise
        except (RuntimeError, ValueError) as e:
            logger.error(f"Failed to initialize YOLO model: {e}")
            raise

    def set_confidence(self, confidence: float):
        """Update confidence threshold."""
        self.confidence = max(0.1, min(0.95, confidence))
        logger.info(f"Confidence threshold set to {self.confidence}")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """Detect people in the frame."""
        if self.model is None:
            logger.error("Model not loaded")
            return []

        detections = []

        try:
            # Use smaller image size for faster inference
            results = self.model(frame, conf=self.confidence, classes=[0], verbose=False, imgsz=1280, half=True, device=0, iou=0.45)

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for box in boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                    conf = float(box.conf[0])

                    detection = Detection(
                        bbox=(x1, y1, x2, y2),
                        confidence=conf
                    )
                    detections.append(detection)

            self.last_detection_time = time.time()

        except (RuntimeError, ValueError) as e:
            logger.error(f"YOLO inference error: {e}")
        except cv2.error as e:
            logger.error(f"OpenCV error during detection: {e}")

        return detections

    def draw_detections(self, frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
        """Draw bounding boxes and labels on the frame."""
        frame_copy = frame.copy()

        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = (0, 255, 0)  # Green for person

            # Draw bounding box
            cv2.rectangle(frame_copy, (x1, y1), (x2, y2), color, 2)

            # Create label
            label = f"Person {det.confidence:.2f}"
            if det.gender and det.gender != "Unknown":
                # Build label with gender and age
                label = det.gender
                if det.age is not None:
                    label = f"{det.gender}, {det.age}y"
                color = (255, 0, 0) if det.gender == "Male" else (255, 0, 255)

            # Draw label background
            (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(frame_copy, (x1, y1 - label_h - 10), (x1 + label_w, y1), color, -1)

            # Draw label text
            cv2.putText(frame_copy, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return frame_copy


class InsightFaceAnalyzer:
    """Face analysis using InsightFace for accurate gender, age, and face embeddings."""

    def __init__(self, confidence_threshold: float = 0.6, model_name: str = 'buffalo_l'):
        self.app = None
        self.min_face_size = MIN_FACE_SIZE
        self.confidence_threshold = confidence_threshold
        self.model_name = model_name
        self.model_loaded = False
        self._load_model()

    def _load_model(self):
        """Load InsightFace model."""
        try:
            from insightface.app import FaceAnalysis

            self.app = FaceAnalysis(
                name=self.model_name,
                providers=['CUDAExecutionProvider', 'CPUExecutionProvider']
            )
            self.app.prepare(ctx_id=0, det_size=(1024, 1024))
            self.model_loaded = True
            logger.info(f"InsightFace analyzer initialized ({self.model_name} model)")
        except (RuntimeError, OSError, ValueError) as e:
            logger.error(f"Failed to initialize InsightFace with {self.model_name}: {e}")
            try:
                from insightface.app import FaceAnalysis
                self.app = FaceAnalysis(
                    name=self.model_name,
                    providers=['CPUExecutionProvider']
                )
                self.app.prepare(ctx_id=-1, det_size=(1024, 1024))
                self.model_loaded = True
                logger.info(f"InsightFace analyzer initialized ({self.model_name} - CPU mode)")
            except (ImportError, RuntimeError, OSError, ValueError) as e2:
                logger.error(f"Failed to initialize InsightFace (CPU): {e2}")
                raise
        except ImportError as e:
            logger.error(f"InsightFace package not available: {e}")
            raise

    def analyze(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Dict:
        """Analyze face for gender, age, and get embedding."""
        result = {
            "gender": "Unknown",
            "gender_confidence": 0.0,
            "age": None,
            "age_group": "Unknown",
            "embedding": None
        }

        if self.app is None:
            return result

        try:
            x1, y1, x2, y2 = bbox

            # Add padding to bbox for better face detection
            padding = 30
            h, w = frame.shape[:2]
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)

            person_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]

            if person_crop.size == 0 or person_crop.shape[0] < self.min_face_size or person_crop.shape[1] < self.min_face_size:
                return result

            # Detect faces in the person crop
            faces = self.app.get(person_crop)

            if not faces:
                return result

            # Get the largest face (most likely the main person)
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

            # Validate minimum face size
            face_w = face.bbox[2] - face.bbox[0]
            face_h = face.bbox[3] - face.bbox[1]
            if face_w < self.min_face_size or face_h < self.min_face_size:
                return result

            # Extract gender (0 = female, 1 = male in InsightFace)
            if hasattr(face, 'gender') and face.gender is not None:
                gender_val = int(face.gender)
                if gender_val == 1:
                    result["gender"] = "Male"
                    result["gender_confidence"] = 0.9
                else:
                    result["gender"] = "Female"
                    result["gender_confidence"] = 0.9

            # Extract age
            if hasattr(face, 'age') and face.age is not None:
                age = int(face.age)
                result["age"] = age
                result["age_group"] = get_age_group(age)

            # Extract face embedding for re-identification
            if hasattr(face, 'embedding') and face.embedding is not None:
                result["embedding"] = face.embedding

            return result

        except (RuntimeError, ValueError, cv2.error) as e:
            logger.debug(f"InsightFace analysis failed: {e}")
            return result
        except (IndexError, TypeError, AttributeError) as e:
            logger.debug(f"InsightFace result parsing error: {e}")
            return result

    def get_embedding(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        """Get face embedding only (faster if we don't need age/gender)."""
        result = self.analyze(frame, bbox)
        return result.get("embedding")


class EnsembleAnalyzer:
    """Ensemble face analyzer combining InsightFace + DeepFace for better accuracy."""

    def __init__(self, confidence_threshold: float = 0.6):
        self.insightface = InsightFaceAnalyzer(confidence_threshold, model_name='buffalo_l')
        self.use_deepface = True
        self.min_face_size = MIN_FACE_SIZE
        logger.info("Ensemble analyzer initialized: InsightFace (buffalo_l) + DeepFace")

    def _analyze_with_deepface(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Dict:
        """Analyze face using DeepFace as secondary model."""
        result = {
            "gender": "Unknown",
            "gender_confidence": 0.0,
            "age": None,
            "age_group": "Unknown"
        }

        try:
            from deepface import DeepFace

            x1, y1, x2, y2 = bbox
            padding = 20
            h, w = frame.shape[:2]
            x1_pad = max(0, x1 - padding)
            y1_pad = max(0, y1 - padding)
            x2_pad = min(w, x2 + padding)
            y2_pad = min(h, y2 + padding)

            person_crop = frame[y1_pad:y2_pad, x1_pad:x2_pad]

            if person_crop.size == 0 or person_crop.shape[0] < self.min_face_size or person_crop.shape[1] < self.min_face_size:
                return result

            analysis = DeepFace.analyze(
                img_path=person_crop,
                actions=['gender', 'age'],
                enforce_detection=False,
                detector_backend='opencv',
                silent=True
            )

            if isinstance(analysis, list):
                analysis = analysis[0]

            # Extract gender
            gender_data = analysis.get('gender', {})
            male_conf = gender_data.get('Man', 0.0)
            female_conf = gender_data.get('Woman', 0.0)

            if male_conf > female_conf:
                result["gender"] = "Male"
                result["gender_confidence"] = male_conf / 100.0 if male_conf > 1.0 else male_conf
            else:
                result["gender"] = "Female"
                result["gender_confidence"] = female_conf / 100.0 if female_conf > 1.0 else female_conf

            # Extract age
            age = analysis.get('age', None)
            if age is not None:
                result["age"] = int(age)
                result["age_group"] = get_age_group(int(age))

            return result

        except ImportError as e:
            logger.debug(f"DeepFace not available: {e}")
            self.use_deepface = False
            return result
        except (RuntimeError, ValueError, cv2.error) as e:
            logger.debug(f"DeepFace analysis failed: {e}")
            return result
        except (IndexError, TypeError, KeyError) as e:
            logger.debug(f"DeepFace result parsing error: {e}")
            return result

    def analyze(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Dict:
        """Analyze face using ensemble of models."""
        # Get InsightFace prediction (primary)
        insightface_result = self.insightface.analyze(frame, bbox)

        # Get DeepFace prediction (secondary, for ensemble)
        deepface_result = self._analyze_with_deepface(frame, bbox) if self.use_deepface else None

        # Ensemble logic
        final_result = {
            "gender": "Unknown",
            "gender_confidence": 0.0,
            "age": None,
            "age_group": "Unknown",
            "embedding": insightface_result.get("embedding")  # Always from InsightFace
        }

        # Gender: Majority voting
        gender_votes = []
        if insightface_result.get("gender") != "Unknown":
            gender_votes.append((insightface_result["gender"], insightface_result.get("gender_confidence", 0.5)))

        if deepface_result and deepface_result.get("gender") != "Unknown":
            gender_votes.append((deepface_result["gender"], deepface_result.get("gender_confidence", 0.5)))

        if gender_votes:
            # Weighted majority vote (by confidence)
            male_score = sum(conf for gender, conf in gender_votes if gender == "Male")
            female_score = sum(conf for gender, conf in gender_votes if gender == "Female")

            if male_score > female_score:
                final_result["gender"] = "Male"
                final_result["gender_confidence"] = male_score / len(gender_votes)
            elif female_score > male_score:
                final_result["gender"] = "Female"
                final_result["gender_confidence"] = female_score / len(gender_votes)

        # Age: Average prediction
        age_predictions = []
        if insightface_result.get("age") is not None:
            age_predictions.append(insightface_result["age"])

        if deepface_result and deepface_result.get("age") is not None:
            age_predictions.append(deepface_result["age"])

        if age_predictions:
            avg_age = int(sum(age_predictions) / len(age_predictions))
            final_result["age"] = avg_age
            final_result["age_group"] = get_age_group(avg_age)

        return final_result


class VisitorTracker:
    """Track unique visitors using face embeddings to prevent double-counting.

    Uses cosine similarity to compare face embeddings and determine if
    a detected person is a new visitor or someone already seen.

    Features:
    - Multiple embeddings per visitor for better matching
    - Confirmation system: must be detected multiple times before counting
    - Pending visitors: unconfirmed detections that need more evidence
    - Median age aggregation across sightings for stable demographics
    - Max visitor cap to bound memory usage
    """

    MAX_ACTIVE_VISITORS = 500

    def __init__(self, similarity_threshold: float = 0.45, memory_duration: int = 1800,
                 confirmation_count: int = 3, pending_timeout: float = 30.0):
        """
        Args:
            similarity_threshold: Cosine similarity threshold (0-1). Lower = more lenient matching.
            memory_duration: How long to remember visitors in seconds (default: 30 minutes)
            confirmation_count: How many times a new visitor must be detected before counting
            pending_timeout: How long to wait for confirmation before discarding pending visitor
        """
        self.similarity_threshold = similarity_threshold
        self.memory_duration = memory_duration
        self.confirmation_count = confirmation_count
        self.pending_timeout = pending_timeout

        # Initialize state persistence
        self.state_persistence = VisitorStatePersistence()
        self.last_save_time = time.time()
        self.save_interval = 30.0  # Save every 30 seconds
        self._id_lock = threading.Lock()

        # Try to restore state from disk
        self._restore_state()

        self.max_embeddings_per_visitor = 5

        logger.info(f"VisitorTracker initialized: similarity={similarity_threshold}, confirmations={confirmation_count}")
        logger.info("Multi-biometric fusion enabled: Face(60%) + Gender(20%) + Age(10%) + Temporal(10%)")

    def _cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Calculate cosine similarity between two embeddings."""
        if emb1 is None or emb2 is None:
            return 0.0

        emb1_norm = emb1 / (np.linalg.norm(emb1) + 1e-10)
        emb2_norm = emb2 / (np.linalg.norm(emb2) + 1e-10)

        similarity = np.dot(emb1_norm, emb2_norm)
        return float(similarity)

    def _get_best_similarity(self, embedding: np.ndarray, visitor_embeddings: list) -> float:
        """Get the best similarity score against a list of embeddings."""
        if not visitor_embeddings:
            return 0.0

        similarities = [self._cosine_similarity(embedding, emb) for emb in visitor_embeddings]
        return max(similarities)

    def _calculate_match_score(self, embedding: np.ndarray, visitor_data: dict,
                                gender: str, age_group: str, current_time: float) -> float:
        """Calculate combined match score using multi-biometric fusion.

        Combines:
        - Face embedding similarity (60%)
        - Gender matching bonus (20%)
        - Age group matching bonus (10%)
        - Temporal recency bonus (10%)

        Returns:
            Combined match score (0.0 - 1.0+)
        """
        # Base embedding similarity (main factor - 60% weight)
        emb_score = self._get_best_similarity(embedding, visitor_data["embeddings"])

        # Gender matching bonus (20% weight)
        stored_gender = visitor_data.get("gender", "Unknown")
        if gender == stored_gender and gender != "Unknown":
            gender_bonus = 0.20
        elif gender == "Unknown" or stored_gender == "Unknown":
            gender_bonus = 0.10
        else:
            gender_bonus = 0.0

        # Age group matching bonus (10% weight)
        stored_age = visitor_data.get("age_group", "Unknown")
        age_bonus = self._calculate_age_bonus(age_group, stored_age)

        # Temporal recency bonus (10% weight)
        time_delta = current_time - visitor_data.get("timestamp", 0)
        if time_delta < 60:
            temporal_bonus = 0.10
        elif time_delta < 300:
            temporal_bonus = 0.07
        elif time_delta < 600:
            temporal_bonus = 0.05
        elif time_delta < 1200:
            temporal_bonus = 0.02
        else:
            temporal_bonus = 0.0

        final_score = emb_score + gender_bonus + age_bonus + temporal_bonus

        return final_score

    def _calculate_age_bonus(self, age1: str, age2: str) -> float:
        """Calculate age group matching bonus based on proximity."""
        if age1 == "Unknown" or age2 == "Unknown":
            return 0.05

        if age1 == age2:
            return 0.10

        age_order = ["Children", "Teens", "Young Adults", "Adults", "Seniors"]
        try:
            idx1 = age_order.index(age1)
            idx2 = age_order.index(age2)
            distance = abs(idx1 - idx2)

            if distance == 1:
                return 0.05
            elif distance == 2:
                return 0.02
            else:
                return 0.0
        except ValueError:
            return 0.0

    def _evict_oldest_visitors(self):
        """Evict oldest visitors when over capacity to bound memory."""
        if len(self.visitors) <= self.MAX_ACTIVE_VISITORS:
            return

        # Sort by timestamp (oldest first) and remove excess
        sorted_ids = sorted(
            self.visitors.keys(),
            key=lambda vid: self.visitors[vid].get("timestamp", 0)
        )
        to_remove = len(self.visitors) - self.MAX_ACTIVE_VISITORS
        for vid in sorted_ids[:to_remove]:
            del self.visitors[vid]
        logger.info(f"Evicted {to_remove} oldest visitors (cap: {self.MAX_ACTIVE_VISITORS})")

    def _cleanup_old_visitors(self):
        """Remove visitors from memory after memory_duration."""
        current_time = time.time()
        expired_ids = [
            vid for vid, data in self.visitors.items()
            if current_time - data["timestamp"] >= self.memory_duration
        ]
        for vid in expired_ids:
            del self.visitors[vid]

    def _cleanup_pending_visitors(self):
        """Remove pending visitors that weren't confirmed in time."""
        current_time = time.time()
        expired_ids = [
            pid for pid, data in self.pending_visitors.items()
            if current_time - data["timestamp"] >= self.pending_timeout
        ]
        for pid in expired_ids:
            del self.pending_visitors[pid]

    def _get_median_age_group(self, age_observations: list) -> Tuple[int, str]:
        """Compute median age and its group from a list of age observations."""
        if not age_observations:
            return None, "Unknown"
        med_age = int(median(age_observations))
        return med_age, get_age_group(med_age)

    def check_visitor(self, embedding: np.ndarray, gender: str, age_group: str, age: Optional[int] = None) -> Tuple[bool, int]:
        """Check if this is a new visitor or someone already seen.

        Uses multi-biometric fusion for improved accuracy plus a confirmation
        system that requires multiple detections before counting.

        Args:
            embedding: Face embedding from InsightFace
            gender: Detected gender
            age_group: Detected age group
            age: Raw age value (for median aggregation)

        Returns:
            Tuple of (is_new_visitor, visitor_id)
        """
        if embedding is None:
            return False, -1

        # Clean up old visitors and pending
        self._cleanup_old_visitors()
        self._cleanup_pending_visitors()
        self._evict_oldest_visitors()

        current_time = time.time()

        # Auto-save state every 30 seconds
        if current_time - self.last_save_time >= self.save_interval:
            self.save_state()

        # Step 1: Check against confirmed visitors using multi-biometric fusion
        best_match_id = -1
        best_score = 0.0
        best_emb_similarity = 0.0

        for visitor_id, data in self.visitors.items():
            score = self._calculate_match_score(embedding, data, gender, age_group, current_time)
            emb_sim = self._get_best_similarity(embedding, data["embeddings"])

            if score > best_score:
                best_score = score
                best_match_id = visitor_id
                best_emb_similarity = emb_sim

        # Match threshold accounts for bonuses
        match_threshold = self.similarity_threshold + 0.15
        if best_score >= match_threshold:
            visitor_data = self.visitors[best_match_id]
            visitor_data["timestamp"] = current_time

            # Update gender if more confident
            if gender != "Unknown" and visitor_data.get("gender") == "Unknown":
                visitor_data["gender"] = gender
            # Record age observation and update via median
            if age is not None:
                visitor_data.setdefault("age_observations", []).append(age)
                med_age, med_group = self._get_median_age_group(visitor_data["age_observations"])
                visitor_data["age_group"] = med_group

            # Add embedding for better future matching
            if best_emb_similarity < 0.85 and len(visitor_data["embeddings"]) < self.max_embeddings_per_visitor:
                visitor_data["embeddings"].append(embedding)

            return False, best_match_id

        # Step 2: Check against pending visitors
        best_pending_id = -1
        best_pending_score = 0.0

        for pending_id, data in self.pending_visitors.items():
            score = self._calculate_match_score(embedding, data, gender, age_group, current_time)
            if score > best_pending_score:
                best_pending_score = score
                best_pending_id = pending_id

        # If matches a pending visitor, increment count
        if best_pending_score >= match_threshold:
            pending_data = self.pending_visitors[best_pending_id]
            pending_data["count"] += 1
            pending_data["embeddings"].append(embedding)
            if age is not None:
                pending_data.setdefault("age_observations", []).append(age)

            # Check if confirmed enough times
            if pending_data["count"] >= self.confirmation_count:
                # Promote to confirmed visitor
                with self._id_lock:
                    visitor_id = self.next_visitor_id
                    self.next_visitor_id += 1

                # Resolve demographics via median age
                final_age_group = pending_data["age_group"]
                age_obs = pending_data.get("age_observations", [])
                if age_obs:
                    _, final_age_group = self._get_median_age_group(age_obs)

                self.visitors[visitor_id] = {
                    "embeddings": pending_data["embeddings"][-self.max_embeddings_per_visitor:],
                    "timestamp": current_time,
                    "gender": pending_data["gender"],
                    "age_group": final_age_group,
                    "age_observations": age_obs,
                }

                # Update stats
                self.stats["total_visitors"] += 1
                if pending_data["gender"] == "Male":
                    self.stats["male"] += 1
                elif pending_data["gender"] == "Female":
                    self.stats["female"] += 1
                else:
                    self.stats["unknown"] += 1

                if final_age_group and final_age_group != "Unknown":
                    if final_age_group in self.stats["age_groups"]:
                        self.stats["age_groups"][final_age_group] += 1
                else:
                    self.stats["age_groups"]["Unknown"] += 1

                # Remove from pending
                del self.pending_visitors[best_pending_id]

                logger.info(f"New visitor #{visitor_id}: {pending_data['gender']}, {final_age_group} (confirmed after {self.confirmation_count} detections)")

                return True, visitor_id

            return False, -1  # Still pending

        # Step 3: Create new pending visitor (always goes through confirmation)
        pending_id = self.next_pending_id
        self.next_pending_id += 1

        self.pending_visitors[pending_id] = {
            "embeddings": [embedding],
            "timestamp": current_time,
            "count": 1,
            "gender": gender,
            "age_group": age_group,
            "age_observations": [age] if age is not None else [],
        }

        return False, -1  # Pending, not counted yet

    def get_active_visitor_count(self) -> int:
        """Get count of visitors currently in memory (recently seen)."""
        self._cleanup_old_visitors()
        return len(self.visitors)

    def get_stats(self) -> Dict:
        """Get current visitor statistics."""
        return self.stats.copy()

    def _restore_state(self):
        """Restore visitor tracking state from disk."""
        state = self.state_persistence.load_state()

        self.visitors = state["visitors"]
        self.pending_visitors = state["pending_visitors"]
        self.stats = state["stats"]
        self.next_visitor_id = state["next_visitor_id"]
        self.next_pending_id = state["next_pending_id"]

        logger.info(
            f"Restored state: {len(self.visitors)} confirmed visitors, "
            f"{self.stats['total_visitors']} total visitors counted"
        )

    def save_state(self):
        """Save current visitor tracking state to disk."""
        self.state_persistence.save_state(
            visitors=self.visitors,
            pending_visitors=self.pending_visitors,
            stats=self.stats,
            next_visitor_id=self.next_visitor_id,
            next_pending_id=self.next_pending_id
        )
        self.last_save_time = time.time()

    def reset_stats(self):
        """Reset all visitor statistics and memory."""
        self.visitors = {}
        self.pending_visitors = {}
        self.next_visitor_id = 1
        self.next_pending_id = 1
        self.stats = {
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
        }
        logger.info("VisitorTracker stats reset")


class DetectionEngine:
    """Combined detection engine for person detection, gender/age classification, and visitor tracking."""

    def __init__(self, gender_threshold: float = 0.6, similarity_threshold: float = 0.45):
        self.person_detector = PersonDetector()
        self.face_analyzer = EnsembleAnalyzer(confidence_threshold=gender_threshold)
        self.visitor_tracker = VisitorTracker(
            similarity_threshold=similarity_threshold,
            memory_duration=1800,  # Remember visitors for 30 minutes
            confirmation_count=3,  # Require 3 detections to confirm
            pending_timeout=30.0,  # Allow 30s to gather confirmations
        )
        self.enable_gender = False

    def set_confidence(self, confidence: float):
        """Set detection confidence threshold."""
        self.person_detector.set_confidence(confidence)

    def set_gender_enabled(self, enabled: bool):
        """Enable or disable gender and age classification."""
        self.enable_gender = enabled

    def set_similarity_threshold(self, threshold: float):
        """Set face similarity threshold for re-identification."""
        self.visitor_tracker.similarity_threshold = max(0.0, min(1.0, threshold))
        logger.info(f"Similarity threshold set to {self.visitor_tracker.similarity_threshold}")

    def process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, List[Detection], Dict]:
        """Process a frame and return annotated frame, detections, and stats."""
        detections = self.person_detector.detect(frame)

        stats = {
            "total_people": len(detections),
            "male": 0,
            "female": 0,
            "unknown": len(detections),
            "new_visitors": 0,
            "age_groups": {
                "Children": 0,
                "Teens": 0,
                "Young Adults": 0,
                "Adults": 0,
                "Seniors": 0,
                "Unknown": len(detections)
            }
        }

        if self.enable_gender:
            for det in detections:
                analysis = self.face_analyzer.analyze(frame, det.bbox)

                det.gender = analysis["gender"]
                det.gender_confidence = analysis["gender_confidence"]
                det.age = analysis["age"]
                det.age_group = analysis["age_group"]
                det.embedding = analysis["embedding"]

                # Check if this is a new visitor using face re-identification
                if analysis["embedding"] is not None:
                    is_new, visitor_id = self.visitor_tracker.check_visitor(
                        analysis["embedding"],
                        analysis["gender"],
                        analysis["age_group"],
                        age=analysis["age"],
                    )
                    det.is_new_visitor = is_new
                    det.visitor_id = visitor_id
                    if is_new:
                        stats["new_visitors"] += 1

                # Update gender stats (for current frame display)
                if analysis["gender"] == "Male":
                    stats["male"] += 1
                    stats["unknown"] -= 1
                elif analysis["gender"] == "Female":
                    stats["female"] += 1
                    stats["unknown"] -= 1

                # Update age group stats (for current frame display)
                if analysis["age_group"] != "Unknown":
                    stats["age_groups"][analysis["age_group"]] += 1
                    stats["age_groups"]["Unknown"] -= 1

        annotated_frame = self.person_detector.draw_detections(frame, detections)

        return annotated_frame, detections, stats

    def get_visitor_stats(self) -> Dict:
        """Get accumulated visitor statistics (unique visitors only)."""
        return self.visitor_tracker.get_stats()

    def reset_visitor_stats(self):
        """Reset visitor tracking stats."""
        self.visitor_tracker.reset_stats()

    def get_active_visitors(self) -> int:
        """Get count of visitors currently being tracked (recently seen)."""
        return self.visitor_tracker.get_active_visitor_count()
