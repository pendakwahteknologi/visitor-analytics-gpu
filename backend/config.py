import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Camera settings — no defaults for credentials
CAMERA_IP = os.getenv("CAMERA_IP")
CAMERA_USERNAME = os.getenv("CAMERA_USERNAME")
CAMERA_PASSWORD = os.getenv("CAMERA_PASSWORD")
CAMERA_RTSP_URL = os.getenv("CAMERA_RTSP_URL")

if not CAMERA_RTSP_URL:
    if not all([CAMERA_IP, CAMERA_USERNAME, CAMERA_PASSWORD]):
        print(
            "ERROR: Set CAMERA_RTSP_URL or all of CAMERA_IP, CAMERA_USERNAME, CAMERA_PASSWORD in .env",
            file=sys.stderr,
        )
        sys.exit(1)
    CAMERA_RTSP_URL = (
        f"rtsp://{CAMERA_USERNAME}:{CAMERA_PASSWORD}@{CAMERA_IP}:554/Streaming/Channels/101"
    )

# Detection settings
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.5"))
GENDER_THRESHOLD = float(os.getenv("GENDER_THRESHOLD", "0.4"))
GENDER_ENABLED = os.getenv("GENDER_ENABLED", "true").lower() == "true"
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")

# Streaming settings
STREAM_FPS = int(os.getenv("STREAM_FPS", "15"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))

# Person detection size filter
MIN_PERSON_W: int = int(os.getenv("MIN_PERSON_W", "50"))
MIN_PERSON_H: int = int(os.getenv("MIN_PERSON_H", "100"))

# Body gender classifier confidence threshold
BODY_GENDER_CONFIDENCE: float = float(os.getenv("BODY_GENDER_CONFIDENCE", "0.70"))

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Security
API_KEY = os.getenv("API_KEY", "")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []

# Embedding encryption (optional — set to enable at-rest encryption)
EMBEDDING_ENCRYPTION_KEY = os.getenv("EMBEDDING_ENCRYPTION_KEY", "")

# Login credentials (for browser-based dashboard access)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", "86400"))  # 24 hours

# Logging
LOG_FILE = os.getenv("LOG_FILE", "logs/visitor-stat.log")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
