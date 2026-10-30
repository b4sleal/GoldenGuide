"""Error boundary: every failure becomes one envelope, logged once, with all response headers."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from backend.api.errors import INTERNAL_ERROR, classify
from backend.domain.errors import DependencyUnavailableError, InvalidInputError

from .conftest import SITE_ORIGIN


class QdrantDown(DependencyUnavailableError):
    """Subclass used to prove subclasses inherit their parent's mapping."""


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (HTTPException(401, "Authentication required"), 401, "unauthenticated"),
        (HTTPException(429, "Too many requests"), 429, "rate_limited"),
        (HTTPException(418, "teapot"), 418, "http_error"),
        (InvalidInputError("Bad settings"), 422, "invalid_input"),
        (QdrantDown("Search is unavailable"), 503, "dependency_unavailable"),
    ],
)
def test_classify_maps_known_errors(exc, status, code):
    public = classify(exc)
    assert (public.status, public.code) == (status, code)


def test_domain_error_exposes_only_public_message():
    exc = DependencyUnavailableError("Search is unavailable", internal_detail="qdrant:6333 refused")
    assert classify(exc).message == "Search is unavailable"


def test_unknown_exception_is_generic_internal_error():
    assert classify(RuntimeError("password=hunter2")) == INTERNAL_ERROR


def _routes(app: FastAPI) -> FastAPI:
    @app.get("/boom")
    async def boom():
        raise RuntimeError("postgres://admin:secret@db-host failed")

    @app.get("/dependency")
    async def dependency():
        raise DependencyUnavailableError("Course data is temporarily unavailable")

    return app


def test_unexpected_error_returns_envelope_with_all_headers(app):
    client = TestClient(_routes(app))
    with capture_logs() as logs:
        response = client.get("/boom", headers={"Origin": SITE_ORIGIN})

    body = response.json()
    assert response.status_code == 500
    assert body["error"]["code"] == "internal_error"
    # Internals never leak to the client.
    assert "secret" not in response.text
    # The ID in the body matches the header and the log line, so reports can be traced.
    assert body["error"]["request_id"] == response.headers["x-request-id"]
    # Error responses still pass through CORS and security-header middleware.
    assert response.headers["access-control-allow-origin"] == SITE_ORIGIN
    assert "content-security-policy" in response.headers
    # Exactly one traceback log for the failure.
    failures = [entry for entry in logs if entry["event"] == "request.failed"]
    assert len(failures) == 1
    assert failures[0]["error_type"] == "RuntimeError"


def test_domain_error_maps_to_status_and_public_message(app):
    response = TestClient(_routes(app)).get("/dependency")
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "dependency_unavailable",
        "message": "Course data is temporarily unavailable",
        "request_id": response.headers["x-request-id"],
        "trace_id": None,
    }


def test_client_errors_are_not_logged_as_failures(app):
    with capture_logs() as logs:
        response = TestClient(app).get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert not [entry for entry in logs if entry["event"] == "request.failed"]
