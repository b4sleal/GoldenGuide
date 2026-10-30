"""Chat stream protocol: success ends with "ok"; failures are an HTTP error or an "error" event."""
import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from backend.api.streaming import ndjson_stream
from backend.domain.errors import DependencyUnavailableError


def _line(event: dict) -> str:
    return json.dumps(event) + "\n"


async def _answer():
    yield _line({"type": "text", "text": "CP317 requires "})
    yield _line({"type": "text", "text": "CP213."})
    yield _line({"type": "sources", "sources": []})


async def _fails_mid_stream():
    yield _line({"type": "text", "text": "Partial"})
    raise RuntimeError("LLM connection reset")


async def _fails_before_first_event():
    raise DependencyUnavailableError("Course data is temporarily unavailable")
    yield  # pragma: no cover - makes this an async generator


async def _empty():
    return
    yield  # pragma: no cover


def _client(app: FastAPI, events) -> TestClient:
    @app.post("/stream")
    async def stream(request: Request):
        return await ndjson_stream(request, events())

    return TestClient(app)


def _events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line]


def test_complete_answer_ends_with_ok(app):
    response = _client(app, _answer).post("/stream")
    events = _events(response)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [event["type"] for event in events] == ["text", "text", "sources", "ok"]


def test_mid_stream_failure_ends_with_error_and_no_ok(app):
    response = _client(app, _fails_mid_stream).post("/stream")
    events = _events(response)
    assert [event["type"] for event in events] == ["text", "error"]
    assert events[-1]["error"]["code"] == "internal_error"
    assert events[-1]["error"]["request_id"] == response.headers["x-request-id"]
    assert "connection reset" not in response.text


def test_failure_before_first_event_is_a_real_http_error(app):
    response = _client(app, _fails_before_first_event).post("/stream")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "dependency_unavailable"


def test_empty_stream_is_reported_as_server_error(app):
    response = _client(app, _empty).post("/stream")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
