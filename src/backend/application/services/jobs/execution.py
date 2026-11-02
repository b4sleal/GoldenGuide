"""Run one recorded job: heartbeat while it works, and never leave its run unfinished.

Shared by every place a job runs (the in-process launcher in development, the worker later), so the
heartbeat and failure rules live in one place:

- A run that is no longer QUEUED is skipped: it already ran or was failed (e.g. by the zombie sweep),
  so running it again would duplicate work. This makes re-delivery of the same run harmless.
- The job records its own outcome on the run. If it returns or raises without one, or is cancelled
  (shutdown), the run and its unfinished batches are marked FAILED with the reason.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

import structlog
from pydantic import ValidationError

from backend.application.services.jobs.registry import JobRegistry
from backend.domain.entities.job_requests import JobRequest, parse_job_request
from backend.domain.entities.jobs import (
    JobBatchStatus,
    JobBatchUpdate,
    JobFailureReason,
    JobRunMetadataKey,
    JobRunRead,
    JobRunUpdate,
    JobStatus,
)
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.app.query_types import JobRunPageParams
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter

logger = structlog.get_logger(__name__)

UNFINISHED = (JobStatus.QUEUED, JobStatus.RUNNING)


class JobExecution:
    """JobRunExecutor (domain/ports/jobs/batch_jobs.py) used by every launcher and worker."""

    def __init__(self, app_db: AppDB, registry: JobRegistry, heartbeat_seconds: float) -> None:
        self.app_db = app_db
        self.registry = registry
        self.heartbeat_seconds = heartbeat_seconds

    async def run(self, run_id: int, request: JobRequest) -> None:
        """Run `request` for `run_id` to a final run status. Re-raises cancellation only."""
        if await self._queued_run(run_id) is None:
            logger.warning("job_run_not_queued_skipped", run_id=run_id, job=request.key.value)
            return
        await self._execute(run_id, request)

    async def run_stored(self, run_id: int) -> None:
        """Run the request stored on the run at submission (job_submit.py). Re-raises cancellation only.

        Workers receive only the run id, so `job_runs` stays the single source of a job's parameters.
        A run whose request cannot be read is failed instead of guessed at.
        """
        run = await self._queued_run(run_id)
        if run is None:
            logger.warning("job_run_not_queued_skipped", run_id=run_id)
            return
        try:
            request = parse_job_request((run.metadata_json or {})[JobRunMetadataKey.REQUEST])
        except (KeyError, ValidationError):
            logger.exception("job_request_unreadable", run_id=run_id, job_name=run.job_name)
            await self.fail_if_unfinished(run_id, JobFailureReason.INVALID_REQUEST)
            return
        await self._execute(run_id, request)

    async def _execute(self, run_id: int, request: JobRequest) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(run_id), name=f"job-heartbeat-{run_id}")
        try:
            await self.registry.run(run_id, request)
            await self.fail_if_unfinished(run_id, JobFailureReason.MISSING_OUTCOME)
            logger.info("job_execution_finished", run_id=run_id, job=request.key.value)
        except asyncio.CancelledError:
            await self.fail_if_unfinished(run_id, JobFailureReason.INTERRUPTED)
            raise
        except Exception:
            # The job's runner already recorded its error on the run; this is the process-level record.
            logger.exception("job_failed", run_id=run_id, job=request.key.value)
            await self.fail_if_unfinished(run_id, JobFailureReason.EXECUTION_ERROR)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

    async def fail_if_unfinished(self, run_id: int, reason: JobFailureReason) -> None:
        """Mark the run and its unfinished batches FAILED unless the run already reached a final status."""
        try:
            async with self.app_db.start() as repos:
                changed = await repos.jobs.update_runs(
                    update_model=JobRunUpdate(status=JobStatus.FAILED, finished_at=datetime.now(UTC)),
                    filters=JobRunFilter(id=run_id, statuses=UNFINISHED),
                )
                if not changed:
                    # Failed elsewhere (e.g. by the job's own error handling): still close its batches.
                    runs = await repos.jobs.fetch_runs(
                        page_params=JobRunPageParams(limit=1), filters=JobRunFilter(id=run_id),
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
                            run_id=run_id, statuses=(JobBatchStatus.QUEUED, JobBatchStatus.RUNNING),
                        ),
                    )
        except Exception:
            logger.exception("job_failure_not_recorded", run_id=run_id)

    async def _queued_run(self, run_id: int) -> JobRunRead | None:
        """The run if it is still QUEUED; None if it is missing or already ran (or was failed)."""
        async with self.app_db.start() as repos:
            runs = await repos.jobs.fetch_runs(page_params=JobRunPageParams(limit=1), filters=JobRunFilter(id=run_id))
        return runs[0] if runs and runs[0].status == JobStatus.QUEUED else None

    async def _heartbeat(self, run_id: int) -> None:
        while True:
            try:
                async with self.app_db.start() as repos:
                    await repos.jobs.heartbeat_run(run_id)
            except Exception:
                # A missed beat is tolerated: the zombie timeout covers several heartbeats.
                logger.warning("job_heartbeat_failed", run_id=run_id, exc_info=True)
            await asyncio.sleep(self.heartbeat_seconds)
