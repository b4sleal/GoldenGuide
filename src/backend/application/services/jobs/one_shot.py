"""One-shot job runner: record a single unit of work (e.g. a whole crawl) with the batch-job model.

The work runs as one synthetic batch, so one-shot and batch jobs share run/batch status, history and
the admin views. Any failure is stored FAILED with its error and then re-raised to the caller.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from backend.application.services.jobs.job_runner import error_details
from backend.domain.entities.jobs import (
    JobBatchCreate,
    JobBatchParams,
    JobBatchStatus,
    JobBatchUpdate,
    JobMode,
    JobRunUpdate,
    JobStatus,
    JobWorkResult,
    JsonObject,
)
from backend.domain.errors import ConflictError
from backend.domain.ports.jobs.batch_jobs import BatchAuditor
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter


class OneShotJobRunner:
    """Records a single unit of work as a run with one synthetic batch, so it shares the batch-job status/history model."""

    def __init__(
            self,
            app_db: AppDB,
            job_name: str,
            auditor: BatchAuditor | None = None,
    ) -> None:
        self.app_db = app_db
        self.job_name = job_name
        self.auditor = auditor

    async def execute(
            self,
            *,
            run_id: int,
            mode: JobMode,
            work: Callable[[], Awaitable[JobWorkResult]],
            metadata: dict | None = None,
    ) -> JsonObject:
        batch = JobBatchParams(batch_no=1, offset=0, batch_size=1)

        async with self.app_db.start() as repos:
            changed = await repos.jobs.update_runs(
                update_model=JobRunUpdate(status=JobStatus.RUNNING, started_at=datetime.now(UTC)),
                filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED,)),
            )
            if changed == 0:
                raise ConflictError("Job run is no longer queued")

            await repos.jobs.upsert_batches([
                JobBatchCreate(
                    run_id=run_id,
                    batch_no=batch.batch_no,
                    offset=batch.offset,
                    batch_size=batch.batch_size,
                    status=JobBatchStatus.RUNNING
                )
            ])

            await repos.jobs.update_batches(
                update_model=JobBatchUpdate(started_at=datetime.now(UTC)),
                filters=JobBatchFilter(run_id=run_id, batch_no=batch.batch_no, statuses=(JobBatchStatus.RUNNING,))
            )

        try:
            outcome = await work()
            summary = outcome.summary
            audit = await self.auditor.run_audit() if self.auditor else None

            final_metadata = {
                "mode": mode.value,
                "metadata": metadata,
                "summary": summary,
                "audit": audit,
            }

            async with self.app_db.start() as repos:
                await repos.jobs.update_batches(
                    update_model=JobBatchUpdate(
                        status=JobBatchStatus.SUCCESS if outcome.status == JobStatus.SUCCESS else JobBatchStatus.FAILED,
                        processed_count=1, metadata_json=summary,
                        error_type=None if outcome.status == JobStatus.SUCCESS else "IncompleteRetrieval",
                        error_message=None if outcome.status == JobStatus.SUCCESS else "Some source data could not be retrieved",
                        finished_at=datetime.now(UTC)
                    ),
                    filters=JobBatchFilter(run_id=run_id, batch_no=batch.batch_no, statuses=(JobBatchStatus.RUNNING,))
                )

                await repos.jobs.update_runs(
                    update_model=JobRunUpdate(status=outcome.status, metadata_json=final_metadata, finished_at=datetime.now(UTC)),
                    filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED, JobStatus.RUNNING))
                )

            return {
                "job_name": self.job_name,
                "run_id": run_id,
                **final_metadata,
            }

        # Record work, audit, or finalization errors as FAILED, then re-raise when persistence succeeds.
        except Exception as exc:
            error = error_details(exc)

            async with self.app_db.start() as repos:
                await repos.jobs.update_batches(
                    update_model=JobBatchUpdate(
                        status=JobBatchStatus.FAILED, error_type=error["error_type"], error_message=error["error_message"],
                        finished_at=datetime.now(UTC)
                    ),
                    filters=JobBatchFilter(run_id=run_id, batch_no=batch.batch_no, statuses=(JobBatchStatus.RUNNING,))
                )

                await repos.jobs.update_runs(
                    update_model=JobRunUpdate(
                        status=JobStatus.FAILED, metadata_json={"mode": mode.value, "metadata": metadata, "error": error}, finished_at=datetime.now(UTC)
                    ),
                    filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED, JobStatus.RUNNING))
                )

            raise
