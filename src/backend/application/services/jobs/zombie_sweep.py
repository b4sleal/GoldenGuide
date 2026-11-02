"""Periodically fail job runs that can no longer finish (see JobRepository.fail_zombie_jobs).

Runs in whichever process runs jobs: the API with in-process execution, each worker otherwise
(runtime.py, worker.py). Several sweepers at once are safe: a run is only failed after it has been
silent (RUNNING) or waiting (QUEUED) for the whole timeout, wherever it runs.
"""
import asyncio

import structlog

from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.settings.jobs import JobSettings

logger = structlog.get_logger(__name__)


async def sweep_once(app_db: AppDB, settings: JobSettings) -> int:
    async with app_db.start() as repos:
        failed = await repos.jobs.fail_zombie_jobs(
            heartbeat_timeout_minutes=settings.zombie_timeout_minutes,
            queued_timeout_minutes=settings.queued_timeout_minutes,
        )
    if failed:
        logger.warning(
            "job_zombies_failed",
            runs=failed,
            heartbeat_timeout_minutes=settings.zombie_timeout_minutes,
            queued_timeout_minutes=settings.queued_timeout_minutes,
        )
    return failed


async def sweep_forever(app_db: AppDB, settings: JobSettings) -> None:
    while True:
        try:
            await sweep_once(app_db, settings)
        except Exception:
            # A failed sweep is retried on the next tick; it must not stop the loop.
            logger.exception("job_zombie_sweep_failed")
        await asyncio.sleep(settings.zombie_sweep_seconds)
