"""Periodically fail job runs that stopped showing signs of life (see JobRepository.fail_zombie_jobs).

Runs for the life of each API process. With several replicas, each sweeps; that is safe because a
run is only failed after its heartbeat has been missing for the whole timeout, wherever it runs.
"""
import asyncio

import structlog

from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.settings.jobs import JobSettings

logger = structlog.get_logger(__name__)


async def sweep_once(app_db: AppDB, settings: JobSettings) -> int:
    async with app_db.start() as repos:
        failed = await repos.jobs.fail_zombie_jobs(timeout_minutes=settings.zombie_timeout_minutes)
    if failed:
        logger.warning("job_zombies_failed", runs=failed, timeout_minutes=settings.zombie_timeout_minutes)
    return failed


async def sweep_forever(app_db: AppDB, settings: JobSettings) -> None:
    while True:
        try:
            await sweep_once(app_db, settings)
        except Exception:
            # A failed sweep is retried on the next tick; it must not stop the loop.
            logger.exception("job_zombie_sweep_failed")
        await asyncio.sleep(settings.zombie_sweep_seconds)
