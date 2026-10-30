"""Shutdown cleans up background jobs; failed startup never constructs a launcher."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.startup import runtime


def app_with(startup_error=None, shutdown_error=None):
    launcher = SimpleNamespace(shutdown=AsyncMock(side_effect=shutdown_error))
    container = SimpleNamespace(
        startup_runner=Mock(
            return_value=SimpleNamespace(
                initialize=AsyncMock(side_effect=startup_error)
            )
        ),
        services=SimpleNamespace(job_launcher=Mock(return_value=launcher)),
        persistence=SimpleNamespace(app_db=Mock(return_value=object())),
        app_config=Mock(
            return_value=SimpleNamespace(system=SimpleNamespace(jobs=object()))
        ),
    )
    return SimpleNamespace(
        container=container, state=SimpleNamespace(oidc=None)
    ), launcher


async def test_lifespan_stops_sweep_and_jobs_and_flushes_telemetry(monkeypatch):
    stopped = asyncio.Event()

    async def sweep(*args):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(runtime, "sweep_forever", sweep)
    flush = Mock()
    monkeypatch.setattr(runtime, "shutdown_telemetry", flush)
    app, launcher = app_with()
    async with runtime.lifespan(app):
        await asyncio.sleep(0)
    assert stopped.is_set()
    launcher.shutdown.assert_awaited_once()
    flush.assert_called_once()


async def test_failed_startup_flushes_without_constructing_launcher(monkeypatch):
    flush = Mock()
    monkeypatch.setattr(runtime, "shutdown_telemetry", flush)
    app, launcher = app_with(startup_error=RuntimeError("startup failed"))
    with pytest.raises(RuntimeError):
        async with runtime.lifespan(app):
            pytest.fail("startup unexpectedly succeeded")
    app.container.services.job_launcher.assert_not_called()
    launcher.shutdown.assert_not_awaited()
    flush.assert_called_once()
