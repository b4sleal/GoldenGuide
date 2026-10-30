"""WebSocket handshakes are refused cleanly; health probes don't flood the access log."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from structlog.testing import capture_logs


def test_websocket_handshake_is_refused_without_error(app):
    with capture_logs() as logs, pytest.raises(WebSocketDisconnect) as exc:
        with TestClient(app).websocket_connect("/"):
            pass
    assert exc.value.code == 1008
    assert not [entry for entry in logs if entry["log_level"] == "error"]


def test_successful_health_probe_is_not_access_logged(app):
    with capture_logs() as logs:
        assert TestClient(app).get("/health/live").status_code == 200
    assert not [entry for entry in logs if entry["event"] == "http.completed"]


def test_other_requests_are_still_access_logged(app):
    with capture_logs() as logs:
        TestClient(app).get("/api/v1/does-not-exist")
    (entry,) = [e for e in logs if e["event"] == "http.completed"]
    assert entry["status_code"] == 404
