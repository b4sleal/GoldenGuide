"""Shutdown cleans up background jobs; failed startup never constructs a launcher."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.core.startup import runtime
from backend.domain.settings.jobs import JobExecutionMode


def app_with(startup_error=None, shutdown_error=None, execution=JobExecutionMode.IN_PROCESS):
    launcher = SimpleNamespace(shutdown=AsyncMock(side_effect=shutdown_error))
    queue_app = SimpleNamespace(open_async=AsyncMock(), close_async=AsyncMock())
    container = SimpleNamespace(
        startup_runner=Mock(
            return_value=SimpleNamespace(
                initialize=AsyncMock(side_effect=startup_error)
            )
        ),
        services=SimpleNamespace(
            job_launcher=Mock(return_value=launcher), procrastinate_app=Mock(return_value=queue_app),
        ),
        persistence=SimpleNamespace(app_db=Mock(return_value=object())),
        app_config=Mock(
            return_value=SimpleNamespace(system=SimpleNamespace(jobs=SimpleNamespace(execution=execution)))
        ),
    )
    return SimpleNamespace(
        container=container, state=SimpleNamespace(oidc=None)
    ), launcher, queue_app


@pytest.fixture
def sweep(monkeypatch):
    state = SimpleNamespace(started=asyncio.Event(), stopped=asyncio.Event())

    async def fake_sweep(*args):
        state.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            state.stopped.set()

    monkeypatch.setattr(runtime, "sweep_forever", fake_sweep)
    return state


async def test_lifespan_stops_sweep_and_jobs_and_flushes_telemetry(monkeypatch, sweep):
    flush = Mock()
    monkeypatch.setattr(runtime, "shutdown_telemetry", flush)
    app, launcher, _ = app_with()
    async with runtime.lifespan(app):
        await asyncio.sleep(0)
    assert sweep.stopped.is_set()
    launcher.shutdown.assert_awaited_once()
    flush.assert_called_once()
    # In-process execution never touches the job queue.
    app.container.services.procrastinate_app.assert_not_called()


async def test_worker_execution_opens_the_job_queue_and_leaves_the_sweep_to_workers(monkeypatch, sweep):
    monkeypatch.setattr(runtime, "shutdown_telemetry", Mock())
    app, launcher, queue_app = app_with(execution=JobExecutionMode.WORKER)
    async with runtime.lifespan(app):
        queue_app.open_async.assert_awaited_once()
        queue_app.close_async.assert_not_awaited()
        await asyncio.sleep(0)
        assert not sweep.started.is_set()  # Workers sweep (backend/worker.py), not the API.
    queue_app.close_async.assert_awaited_once()
    launcher.shutdown.assert_awaited_once()


async def test_failed_startup_flushes_without_constructing_launcher(monkeypatch):
    flush = Mock()
    monkeypatch.setattr(runtime, "shutdown_telemetry", flush)
    app, launcher, queue_app = app_with(startup_error=RuntimeError("startup failed"))
    with pytest.raises(RuntimeError):
        async with runtime.lifespan(app):
            pytest.fail("startup unexpectedly succeeded")
    app.container.services.job_launcher.assert_not_called()
    launcher.shutdown.assert_not_awaited()
    queue_app.open_async.assert_not_awaited()
    flush.assert_called_once()
