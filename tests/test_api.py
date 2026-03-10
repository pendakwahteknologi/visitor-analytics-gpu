"""Integration tests for FastAPI endpoints.

Uses TestClient (synchronous) to exercise the API without starting
the full CCTV pipeline.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure env is set before importing the app
os.environ["CAMERA_RTSP_URL"] = "rtsp://test:test@127.0.0.1:554/test"
os.environ["API_KEY"] = "test-secret-key"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["SESSION_SECRET"] = "test-session-secret-key"
os.environ["TZ"] = "UTC"


@pytest.fixture(scope="module")
def client():
    """Create a test client with mocked CCTV and detection components."""
    # Patch heavy components before importing main
    with patch("main.CCTVHandler") as MockCCTV, \
         patch("main.DetectionEngine") as MockEngine, \
         patch("main.StreamManager") as MockStream:

        mock_cctv = MockCCTV.return_value
        mock_cctv.is_connected = False
        mock_cctv.connection_state = "disconnected"
        mock_cctv.is_running.return_value = False
        mock_cctv.start.return_value = None
        mock_cctv.stop.return_value = None

        mock_engine = MockEngine.return_value
        mock_engine.person_detector.confidence = 0.5
        mock_engine.person_detector.model_loaded = True
        mock_engine.person_detector.last_detection_time = None
        mock_engine.face_analyzer.insightface.model_loaded = True
        mock_engine.enable_gender = True
        mock_engine.get_visitor_stats.return_value = {
            "total_visitors": 10, "male": 5, "female": 4, "unknown": 1,
            "age_groups": {
                "Children": 1, "Teens": 2, "Young Adults": 3,
                "Adults": 2, "Seniors": 1, "Unknown": 1,
            },
        }
        mock_engine.get_active_visitors.return_value = 3
        mock_engine.set_gender_enabled.return_value = None
        mock_engine.set_confidence.return_value = None
        mock_engine.reset_visitor_stats.return_value = None

        mock_stream = MockStream.return_value
        mock_stream.streaming = False
        mock_stream.connection_manager.connection_count = 0
        mock_stream.get_stats.return_value = {
            "current": {
                "total_people": 2, "male": 1, "female": 1, "unknown": 0,
                "fps": 15,
                "age_groups": {
                    "Children": 0, "Teens": 0, "Young Adults": 1,
                    "Adults": 1, "Seniors": 0, "Unknown": 0,
                },
            },
            "session": {
                "total_detected": 10, "male_detected": 5, "female_detected": 4,
                "age_groups": {
                    "Children": 1, "Teens": 2, "Young Adults": 3,
                    "Adults": 2, "Seniors": 1, "Unknown": 1,
                },
            },
            "connections": 0,
            "active_visitors": 3,
        }
        mock_stream.start_streaming = AsyncMock()
        mock_stream.stop_streaming = AsyncMock()
        mock_stream.reset_session_stats.return_value = None

        # Now import app (which uses the patched globals)
        import importlib
        import main as main_module
        importlib.reload(main_module)

        # Inject mocks
        main_module.cctv_handler = mock_cctv
        main_module.detection_engine = mock_engine
        main_module.stream_manager = mock_stream

        from fastapi.testclient import TestClient
        with TestClient(main_module.app) as tc:
            yield tc


HEADERS = {"X-API-Key": "test-secret-key"}
BAD_HEADERS = {"X-API-Key": "wrong-key"}


class TestHealthEndpoint:
    def test_health_no_auth_required(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "models" in data


class TestAuthEnforcement:
    def test_stats_requires_key(self, client):
        r = client.get("/stats")
        assert r.status_code == 401

    def test_stats_with_valid_key(self, client):
        r = client.get("/stats", headers=HEADERS)
        assert r.status_code == 200

    def test_stats_with_bad_key(self, client):
        r = client.get("/stats", headers=BAD_HEADERS)
        assert r.status_code == 401

    def test_settings_requires_key(self, client):
        r = client.get("/settings")
        assert r.status_code == 401


class TestSettingsValidation:
    def test_confidence_too_low(self, client):
        r = client.post(
            "/settings",
            json={"confidence": 0.01},
            headers=HEADERS,
        )
        assert r.status_code == 422  # Validation error

    def test_confidence_too_high(self, client):
        r = client.post(
            "/settings",
            json={"confidence": 1.5},
            headers=HEADERS,
        )
        assert r.status_code == 422

    def test_valid_confidence(self, client):
        r = client.post(
            "/settings",
            json={"confidence": 0.5},
            headers=HEADERS,
        )
        assert r.status_code == 200


class TestStatsEndpoints:
    def test_weekly(self, client):
        r = client.get("/stats/weekly", headers=HEADERS)
        assert r.status_code == 200
        assert "total_visitors" in r.json()

    def test_monthly(self, client):
        r = client.get("/stats/monthly", headers=HEADERS)
        assert r.status_code == 200

    def test_all_time(self, client):
        r = client.get("/stats/all-time", headers=HEADERS)
        assert r.status_code == 200

    def test_export_csv(self, client):
        r = client.get("/stats/export", headers=HEADERS)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]


class TestPdfExport:
    def test_pdf_export_requires_auth(self, client):
        response = client.get("/stats/export/pdf")
        assert response.status_code == 401

    def test_pdf_export_returns_pdf(self, client):
        response = client.get("/stats/export/pdf", headers=HEADERS)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "attachment" in response.headers.get("content-disposition", "")
        assert response.content[:5] == b"%PDF-"


class TestResetStats:
    def test_reset(self, client):
        r = client.post("/reset-stats", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["message"] == "Statistics reset"


class TestSecurityHeaders:
    def test_csp_present(self, client):
        r = client.get("/health")
        assert "Content-Security-Policy" in r.headers
        assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]

    def test_x_content_type(self, client):
        r = client.get("/health")
        assert r.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self, client):
        r = client.get("/health")
        assert r.headers["X-Frame-Options"] == "DENY"


class TestLoginFlow:
    def test_root_redirects_to_login(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]

    def test_login_page_accessible(self, client):
        r = client.get("/login")
        assert r.status_code == 200

    def test_login_with_bad_credentials(self, client):
        r = client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
            follow_redirects=False,
        )
        assert r.status_code == 401

    def test_login_with_valid_credentials(self, client):
        r = client.post(
            "/login",
            data={"username": "admin", "password": "test-password"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        assert r.headers["location"] == "/"
        assert "session" in r.cookies

    def test_session_cookie_grants_access(self, client):
        # Login first
        login_r = client.post(
            "/login",
            data={"username": "admin", "password": "test-password"},
            follow_redirects=False,
        )
        session_cookie = login_r.cookies.get("session")
        assert session_cookie

        # Access protected endpoint with session cookie
        r = client.get("/stats", cookies={"session": session_cookie})
        assert r.status_code == 200

    def test_logout_clears_session(self, client):
        r = client.get("/logout", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.headers["location"]
