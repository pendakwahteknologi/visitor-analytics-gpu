"""Shared fixtures for the test suite."""

import os
import sys
import tempfile
import pytest

# Ensure backend modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Set minimal env vars so config.py doesn't sys.exit
os.environ.setdefault("CAMERA_RTSP_URL", "rtsp://test:test@127.0.0.1:554/test")
os.environ.setdefault("TZ", "UTC")


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory for test data files."""
    return tmp_path
