"""Unit tests for CCTVHandler utilities."""

from cctv_handler import _sanitize_url, CCTVHandler


class TestSanitizeURL:
    def test_masks_credentials(self):
        url = "rtsp://admin:SuperSecret123@192.168.1.100:554/Streaming/Channels/101"
        safe = _sanitize_url(url)
        assert "SuperSecret123" not in safe
        assert "admin" not in safe
        assert "****:****" in safe
        assert "192.168.1.100" in safe

    def test_no_credentials(self):
        url = "rtsp://192.168.1.100:554/stream"
        assert _sanitize_url(url) == url

    def test_complex_password(self):
        url = "rtsp://user:p@ss:word@10.0.0.1:554/ch1"
        safe = _sanitize_url(url)
        assert "p@ss" not in safe


class TestReconnectDelay:
    def test_exponential_backoff(self):
        handler = CCTVHandler.__new__(CCTVHandler)
        handler.reconnect_delay_base = 5
        handler.reconnect_delay_max = 60

        assert handler._calculate_reconnect_delay(0) == 5
        assert handler._calculate_reconnect_delay(1) == 10
        assert handler._calculate_reconnect_delay(2) == 20
        assert handler._calculate_reconnect_delay(3) == 40
        assert handler._calculate_reconnect_delay(4) == 60  # capped
        assert handler._calculate_reconnect_delay(10) == 60  # still capped
