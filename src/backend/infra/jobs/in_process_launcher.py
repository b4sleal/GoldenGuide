"""Execute jobs in this API process; persist interruption and recover crashes by heartbeat expiry.

This adapter is not a durable queue: restarts end work, and failed work must be resubmitted.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog

from backend.domain.entities.jobs import (
    JobBatchStatus,
    JobBatchUpdate,
    JobRunUpdate,
    JobStatus,
)
from backend.domain.errors import DependencyUnavailableError
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.app.query_types import JobRunPageParams
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter

logger = structlog.get_logger(__name__)
UNFINISHED = (JobStatus.QUEUED, JobStatus.RUNNING)


class InProcessJobLauncher:
    def __init__(self, app_db: AppDB, heartbeat_seconds: float) -> None:
        self.app_db = app_db
        self.heartbeat_seconds = heartbeat_seconds
        self._tasks: dict[asyncio.Task[None], int] = {}
        self._closed = False

    async def launch(self, run_id: int, work: Callable[[], Awaitable[object]]) -> None:
        if self._closed:
            raise DependencyUnavailableError("Job execution is shutting down")
        task = asyncio.create_task(self._run(run_id, work), name=f"job-run-{run_id}")
        self._tasks[task] = run_id
        task.add_done_callback(self._finished)
        logger.info("job_launched", run_id=run_id)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.pop(task, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error(
                "job_launcher_failed", task=task.get_name(), exc_info=task.exception()
            )

    async def shutdown(self) -> None:
        """Cancel and await work, including jobs cancelled before their first instruction."""
        self._closed = True
        tasks = dict(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for run_id in tasks.values():
            await self._fail_if_unfinished(run_id, "Interrupted")

    async def _run(self, run_id: int, work: Callable[[], Awaitable[object]]) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(run_id))
        try:
            await work()
            await self._fail_if_unfinished(run_id, "MissingOutcome")
            logger.info("job_execution_finished", run_id=run_id)
        except asyncio.CancelledError:
            await self._fail_if_unfinished(run_id, "Interrupted")
            raise
        except Exception:
            logger.exception("job_failed", run_id=run_id)
            await self._fail_if_unfinished(run_id, "ExecutionError")
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def _heartbeat(self, run_id: int) -> None:
        while True:
            try:
                async with self.app_db.start() as repos:
                    await repos.jobs.heartbeat_run(run_id)
            except Exception:
                logger.warning("job_heartbeat_failed", run_id=run_id, exc_info=True)
            await asyncio.sleep(self.heartbeat_seconds)

    async def _fail_if_unfinished(self, run_id: int, reason: str) -> None:
        try:
            async with self.app_db.start() as repos:
                changed = await repos.jobs.update_runs(
                    update_model=JobRunUpdate(
                        status=JobStatus.FAILED, finished_at=datetime.now(UTC)
                    ),
                    filters=JobRunFilter(id=run_id, statuses=UNFINISHED),
                )
                if not changed:
                    runs = await repos.jobs.fetch_runs(
                        page_params=JobRunPageParams(limit=1),
                        filters=JobRunFilter(id=run_id),
                    )
                    changed = bool(runs and runs[0].status == JobStatus.FAILED)
                if changed:
                    await repos.jobs.update_batches(
                        update_model=JobBatchUpdate(
                            status=JobBatchStatus.FAILED,
                            error_type=reason,
                            error_message="Job execution ended before completion",
                            finished_at=datetime.now(UTC),
                        ),
                        filters=JobBatchFilter(
                            run_id=run_id,
                            statuses=(JobBatchStatus.QUEUED, JobBatchStatus.RUNNING),
                        ),
                    )
        except Exception:
            logger.exception("job_failure_not_recorded", run_id=run_id)
