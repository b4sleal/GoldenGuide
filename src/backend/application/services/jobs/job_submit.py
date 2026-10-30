"""Job submission: record a QUEUED run, then hand its work to the launcher and return at once.

Submitting only queues a job; the run's status (GET /admin/jobs/{run_id}), not this call, says
whether the job completed. Two runs of the same job never overlap: a submission while one is QUEUED
or RUNNING is refused (ConflictError), since both would write the same records.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from backend.domain.entities.jobs import (
    JobMode,
    JobRunCreate,
    JobRunQueued,
    JobRunUpdate,
    JobStatus,
    JsonObject,
)
from backend.domain.errors import ConflictError
from backend.domain.ports.jobs.batch_jobs import JobLauncher
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.app.query_types import JobRunPageParams
from backend.domain.ports.repositories.filters import JobRunFilter

ACTIVE_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)


class JobSubmissionService:
    def __init__(self, app_db: AppDB, launcher: JobLauncher) -> None:
        self.app_db = app_db
        self.launcher = launcher

    async def submit(
        self,
        *,
        job_name: str,
        mode: JobMode,
        metadata: JsonObject,
        work: Callable[[int], Awaitable[object]],
    ) -> JobRunQueued:
        """Queue a job that records its own progress on the run it is given (batch and one-shot jobs)."""
        # Check and create under a transaction lock shared by every backend instance.
        async with self.app_db.start() as repos:
            await repos.jobs.lock_submission(job_name)
            active = await repos.jobs.fetch_runs(
                page_params=JobRunPageParams(limit=1),
                filters=JobRunFilter(job_name=job_name, statuses=ACTIVE_STATUSES),
            )
            if active:
                raise ConflictError(
                    f"{job_name} is already running (run {active[0].id})"
                )
            run_id = await repos.jobs.create_run(
                payload=JobRunCreate(
                    job_name=job_name,
                    mode=mode,
                    status=JobStatus.QUEUED,
                    metadata_json=metadata,
                )
            )

        # Step 2: start it. The run is committed first, so it is visible even if launching fails.
        try:
            await self.launcher.launch(run_id, lambda: work(run_id))
        except BaseException:
            async with self.app_db.start() as repos:
                await repos.jobs.update_runs(
                    update_model=JobRunUpdate(
                        status=JobStatus.FAILED, finished_at=datetime.now(UTC)
                    ),
                    filters=JobRunFilter(id=run_id, statuses=ACTIVE_STATUSES),
                )
            raise
        return JobRunQueued(run_id=run_id, job_name=job_name, status=JobStatus.QUEUED)
