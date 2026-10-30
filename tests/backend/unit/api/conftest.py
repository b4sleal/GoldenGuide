"""Shared fixtures: a real create_app() stack with fake configuration and no infrastructure."""
import pytest
from fastapi import FastAPI

from backend.api.app import create_app

SITE_ORIGIN = "http://localhost:8080"


class FakeSecretReader:
    """Minimal SecretReader stand-in backed by a dict."""

    def __init__(self, values: dict[str, str]):
        self.values = values

    def get(self, name: str, default: str | None = None) -> str | None:
        return self.values.get(name, default)


@pytest.fixture
def app() -> FastAPI:
    # Real middleware order and error handlers, as production builds them.
    # TestClient sends Host: testserver, so it must be an allowed host.
    return create_app(FakeSecretReader({
        "SITE_ORIGIN": SITE_ORIGIN,
        "ALLOWED_HOSTS": "testserver",
        "CORS_ORIGINS": SITE_ORIGIN,
        "SERVE_FRONTEND": "false",
    }))
