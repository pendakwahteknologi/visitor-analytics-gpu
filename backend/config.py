import os
from dotenv import load_dotenv

load_dotenv()

# Camera settings
CAMERA_IP = os.getenv("CAMERA_IP", "172.31.0.71")
CAMERA_USERNAME = os.getenv("CAMERA_USERNAME", "admin")
CAMERA_PASSWORD = os.getenv("CAMERA_PASSWORD", "TestingPKNS2026")
CAMERA_RTSP_URL = os.getenv("CAMERA_RTSP_URL", f"rtsp://{CAMERA_USERNAME}:{CAMERA_PASSWORD}@{CAMERA_IP}:554/Streaming/Channels/101")

# Detection settings (relaxed for easier detection)
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.3"))
GENDER_THRESHOLD = float(os.getenv("GENDER_THRESHOLD", "0.4"))
GENDER_ENABLED = os.getenv("GENDER_ENABLED", "true").lower() == "true"
YOLO_MODEL = os.getenv("YOLO_MODEL", "yolov8n.pt")

# Streaming settings
STREAM_FPS = int(os.getenv("STREAM_FPS", "15"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
