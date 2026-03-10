"""WebSocket load tests — concurrent client connections.

Tests that the server can handle multiple simultaneous WebSocket
connections without errors or dropped clients.
"""

import os
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure env is set before importing the app
os.environ["CAMERA_RTSP_URL"] = "rtsp://test:test@127.0.0.1:554/test"
os.environ["API_KEY"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["SESSION_SECRET"] = ""
os.environ["TZ"] = "UTC"


@pytest.fixture(scope="module")
def app():
    """Create the FastAPI app with mocked heavy components."""
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
        mock_engine.get_active_visitors.return_value = 0
        mock_engine.set_gender_enabled.return_value = None

        mock_stream = MockStream.return_value
        mock_stream.streaming = False
        mock_stream.start_streaming = AsyncMock()
        mock_stream.stop_streaming = AsyncMock()

        # Use a real ConnectionManager so websocket.accept() is called
        from streaming import ConnectionManager
        real_cm = ConnectionManager()
        mock_stream.connection_manager = real_cm

        import importlib
        import config as config_module
        importlib.reload(config_module)
        import main as main_module
        importlib.reload(main_module)

        main_module.cctv_handler = mock_cctv
        main_module.detection_engine = mock_engine
        main_module.stream_manager = mock_stream

        yield main_module.app


@pytest.fixture(scope="module")
def base_url(app):
    """Run the app in a background server and return its base URL."""
    import uvicorn
    from threading import Thread

    config = uvicorn.Config(app, host="127.0.0.1", port=9876, log_level="warning")
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to start
    import time
    for _ in range(50):
        try:
            import socket
            s = socket.socket()
            s.connect(("127.0.0.1", 9876))
            s.close()
            break
        except ConnectionRefusedError:
            time.sleep(0.1)

    yield "ws://127.0.0.1:9876"

    server.should_exit = True
    thread.join(timeout=5)


class TestWebSocketConcurrency:
    """Test multiple concurrent WebSocket connections."""

    @pytest.mark.asyncio
    async def test_multiple_clients_connect(self, base_url):
        """10 clients should all connect successfully."""
        import websockets

        num_clients = 10
        connected = 0

        async def connect_client():
            nonlocal connected
            async with websockets.connect(
                f"{base_url}/ws/stream",
                open_timeout=5,
                close_timeout=5,
            ) as ws:
                connected += 1
                # Read the initial status message
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                assert msg  # Should receive status message
                # Send a ping
                await ws.send("ping")
                pong = await asyncio.wait_for(ws.recv(), timeout=5)
                assert pong == "pong"

        tasks = [connect_client() for _ in range(num_clients)]
        await asyncio.gather(*tasks)
        assert connected == num_clients

    @pytest.mark.asyncio
    async def test_rapid_connect_disconnect(self, base_url):
        """20 clients connecting and disconnecting rapidly should not crash the server."""
        import websockets

        successful = 0

        async def rapid_client():
            nonlocal successful
            async with websockets.connect(
                f"{base_url}/ws/stream",
                open_timeout=5,
                close_timeout=5,
            ) as ws:
                # Just connect, read initial message, and disconnect
                await asyncio.wait_for(ws.recv(), timeout=5)
                successful += 1

        tasks = [rapid_client() for _ in range(20)]
        await asyncio.gather(*tasks)
        assert successful == 20

    @pytest.mark.asyncio
    async def test_concurrent_ping_pong(self, base_url):
        """Multiple clients sending pings concurrently should all get pongs."""
        import websockets

        num_clients = 10
        pings_per_client = 5
        total_pongs = 0

        async def ping_client():
            nonlocal total_pongs
            async with websockets.connect(
                f"{base_url}/ws/stream",
                open_timeout=5,
                close_timeout=5,
            ) as ws:
                # Consume initial status
                await asyncio.wait_for(ws.recv(), timeout=5)
                for _ in range(pings_per_client):
                    await ws.send("ping")
                    pong = await asyncio.wait_for(ws.recv(), timeout=5)
                    if pong == "pong":
                        total_pongs += 1

        tasks = [ping_client() for _ in range(num_clients)]
        await asyncio.gather(*tasks)
        assert total_pongs == num_clients * pings_per_client

    @pytest.mark.asyncio
    async def test_staggered_connections(self, base_url):
        """Clients connecting at staggered intervals should all work."""
        import websockets

        results = []

        async def staggered_client(delay: float, client_id: int):
            await asyncio.sleep(delay)
            async with websockets.connect(
                f"{base_url}/ws/stream",
                open_timeout=5,
                close_timeout=5,
            ) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                await ws.send("ping")
                pong = await asyncio.wait_for(ws.recv(), timeout=5)
                results.append((client_id, pong == "pong"))

        tasks = [staggered_client(i * 0.05, i) for i in range(15)]
        await asyncio.gather(*tasks)
        assert len(results) == 15
        assert all(success for _, success in results)

    @pytest.mark.asyncio
    async def test_server_healthy_after_load(self, base_url):
        """After all WebSocket load tests, the HTTP server should still respond."""
        import httpx

        http_url = base_url.replace("ws://", "http://")
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{http_url}/health")
            assert r.status_code == 200
            assert r.json()["status"] == "healthy"
