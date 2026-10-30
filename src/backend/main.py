"""ASGI entry point."""
from backend.api.factory import build_app

app = build_app()
