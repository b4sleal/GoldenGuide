"""Job worker: run queued jobs outside the API process (docs/backend/architecture.md#background-jobs).

    uv run python -m backend.worker                      # locally (Linux/macOS; see below for Windows)
    docker compose --env-file .env.prod up -d worker     # in Docker

Same image, configuration and DI container as the API. The worker claims `run_job(run_id)` tasks
from Procrastinate's queue and runs each through JobExecution, which records progress and outcome
on `job_runs`. On SIGTERM it stops claiming, lets running jobs finish for
`system.jobs.worker.shutdown_graceful_timeout_seconds`, then cancels them (JobExecution marks them
FAILED as Interrupted).

CPU-bound parsing runs in `system.jobs.worker.compute_processes` child processes (ProcessPoolComputeExecutor),
so imports use several cores; the API process keeps parsing on threads.

Windows: psycopg's async mode cannot use Windows' default ProactorEventLoop, so this entrypoint is
meant for Linux containers.
"""
import asyncio
import contextlib
import socket
import sys

import structlog
from dependency_injector import providers

from backend.application.services.jobs.zombie_sweep import sweep_forever
from backend.core.startup.runtime import build_container
from backend.domain.entities.job_requests import JobQueue
from backend.infra.jobs.process_compute import ProcessPoolComputeExecutor
from goldenguide_common.config.env_reader import EnvSecretReader
from goldenguide_common.logging.bootstrap import configure_observability
from goldenguide_common.logging.telemetry import shutdown_telemetry

logger = structlog.get_logger("backend.worker")

# Matches OTEL_SERVICE_NAME of the compose `worker` service; used if that variable is unset.
WORKER_SERVICE_NAME = "goldenguide-worker"

# Procrastinate keeps finished jobs only when asked; job_runs is the record we keep.
DELETE_SUCCESSFUL_QUEUE_JOBS = "successful"


def configure_compute_process() -> None:
    """Runs once in each parsing child process (a fresh interpreter): structured logs like the worker's."""
    configure_observability(EnvSecretReader(), default_service_name=WORKER_SERVICE_NAME)


def use_process_pool(container) -> ProcessPoolComputeExecutor:
    """Parse in parallel child processes in this worker (the API keeps threads).

    Overrides the container's compute executor before any job is built, so every job in this process
    gets the pool.
    """
    pool = ProcessPoolComputeExecutor(
        max_workers=container.app_config().system.jobs.worker.compute_processes,
        initializer=configure_compute_process,
    )
    container.services.compute_executor.override(providers.Object(pool))
    return pool


async def run(container) -> None:
    """Check the schema like the API does, then process queued jobs until stopped.

    The zombie sweep runs here too (with worker execution the API does not sweep): it fails runs whose
    worker died (no heartbeat) and runs that were never picked up (queued_timeout_minutes).
    """
    await container.startup_runner().initialize()
    jobs = container.app_config().system.jobs
    app = container.services.procrastinate_worker_app()
    sweep = asyncio.create_task(sweep_forever(container.persistence.app_db(), jobs), name="job-zombie-sweep")
    try:
        async with app.open_async():
            logger.info("worker.started", concurrency=jobs.worker.concurrency, queues=[q.value for q in JobQueue])
            await app.run_worker_async(
                queues=[queue.value for queue in JobQueue],
                concurrency=jobs.worker.concurrency,
                shutdown_graceful_timeout=jobs.worker.shutdown_graceful_timeout_seconds,
                name=socket.gethostname(),
                delete_jobs=DELETE_SUCCESSFUL_QUEUE_JOBS,
            )
    finally:
        sweep.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweep
    logger.info("worker.stopped")


def main() -> int:
    container = build_container()
    pool = use_process_pool(container)
    try:
        asyncio.run(run(container))
        return 0
    except Exception:
        # Logged once with the traceback; a non-zero exit lets Docker restart the worker.
        logger.exception("worker.failed")
        return 1
    finally:
        pool.shutdown()
        shutdown_telemetry()


if __name__ == "__main__":
    sys.exit(main())
