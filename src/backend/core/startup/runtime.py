"""Per-process bootstrap and startup/shutdown lifecycle for the API backend."""
import asyncio
import contextlib
from contextlib import asynccontextmanager

import structlog
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

from backend.application.services.jobs.zombie_sweep import sweep_forever
from backend.core.di.container import AppContainer
from goldenguide_common.logging.telemetry import shutdown_telemetry

logger = structlog.get_logger("backend.startup")


def build_container() -> AppContainer:
    """Create the DI container with logging, tracing and resources initialized, in that order."""
    container = AppContainer()

    # Step 1: observability first. Logging must be structured before anything else logs, and
    # tracing (including HTTPX instrumentation) must exist before clients are created.
    container.observability_startup()

    # Step 2: one span per SQL statement. This patches `sqlalchemy.ext.asyncio.create_async_engine`,
    # so it must run before any engine is built (Step 3), and the engine code must call it through
    # the module (see infra/persistence/db/db_connection.py). Only parameterized SQL is recorded,
    # never parameter values, so student data in WHERE clauses stays out of traces.
    SQLAlchemyInstrumentor().instrument()

    # Step 3: create resources (DB engines, clients, ...).
    container.init_resources()
    return container


@asynccontextmanager
async def lifespan(app):
    """FastAPI lifespan: startup checks, OIDC discovery and the job sweep; on exit, stop jobs and flush telemetry."""
    container = app.container
    sweep = None
    launcher = None
    try:
        try:
            await container.startup_runner().initialize()
            if app.state.oidc is not None:
                await app.state.oidc.initialize()
        except Exception:
            # One structured record (with traceback) in Loki; the error still stops the replica.
            logger.exception("startup.failed")
            raise
        # Fail runs left unfinished by a previous process, then keep checking (zombie_sweep.py).
        launcher = container.services.job_launcher()
        sweep = asyncio.create_task(
            sweep_forever(container.persistence.app_db(), container.app_config().system.jobs), name="job-zombie-sweep",
        )
        yield
    finally:
        if sweep is not None:
            sweep.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweep
        try:
            if launcher is not None:
                await launcher.shutdown()
        finally:
            shutdown_telemetry()
