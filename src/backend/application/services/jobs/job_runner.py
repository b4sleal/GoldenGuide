"""Batch job runner: split a job into offset-based batches, run them concurrently, persist every state.

Lifecycle of one run (row already committed QUEUED by JobSubmissionService):

    plan batches -> run RUNNING + batches QUEUED -> batches RUNNING -> SUCCESS / FAILED each
    -> optional audit -> run SUCCESS / PARTIAL_SUCCESS / FAILED

A failed batch never aborts the others; it is stored FAILED so a later RETRY run replays only it.
A heartbeat records that the run is alive; fail_zombie_jobs (job repository) can fail runs whose heartbeat
stopped. The launcher owns periodic heartbeats and the lifespan schedules zombie recovery.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from backend.domain.entities.jobs import (
    JobBatchCreate,
    JobBatchParams,
    JobBatchResult,
    JobBatchStatus,
    JobBatchUpdate,
    JobFailedBatch,
    JobMode,
    JobRunMetadataKey,
    JobRunResult,
    JobRunUpdate,
    JobStatus,
)
from backend.domain.errors import ConflictError
from backend.domain.ports.jobs.batch_jobs import BatchAuditor, BatchExecutor
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.app.query_types import (
    JobBatchPageParams,
    JobBatchSortField,
    JobRunPageParams,
    JobRunSortField,
)
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter
from backend.domain.ports.repositories.sorting import SortDirection, SortSpec

logger = structlog.get_logger()

# Stored error messages are cut to this length so one huge traceback cannot bloat a job row.
ERROR_MESSAGE_MAX_CHARS = 5000
MAX_CONCURRENT_BATCHES = 20
# RETRY replays at most this many failed batches of the previous run.
MAX_RETRY_BATCHES = 10000


def error_details(exc: BaseException) -> dict[str, str]:
    """The error fields stored on runs and batches."""
    return {"error_type": exc.__class__.__name__, "error_message": str(exc)[:ERROR_MESSAGE_MAX_CHARS]}


class BatchJobRunner:
    """Runs offset-based batches with bounded concurrency and persisted run/batch state."""

    def __init__(
            self,
            app_db: AppDB,
            job_name: str,
            executor: BatchExecutor,
            auditor: BatchAuditor | None = None,
    ) -> None:
        self.app_db = app_db
        self.job_name = job_name
        self.executor = executor
        self.auditor = auditor

    async def execute(
            self,
            *,
            run_id: int,
            batch_size: int = 200,
            max_concurrent_batches: int = 3,
            mode: JobMode = JobMode.FRESH,
            metadata: dict | None = None,
    ) -> JobRunResult:
        self._validate(batch_size, max_concurrent_batches)

        total_rows, batches = await self._plan_batches(
            batch_size=batch_size,
            mode=mode,
        )

        # No failed batches were found to retry; finish this run successfully.
        if mode is JobMode.RETRY and not batches:
            return await self._complete_empty_retry(
                run_id=run_id,
                batch_size=batch_size,
                max_concurrent_batches=max_concurrent_batches,
                metadata=metadata,
            )

        async with self.app_db.start() as repos:
            changed = await repos.jobs.update_runs(
                update_model=JobRunUpdate(status=JobStatus.RUNNING, started_at=datetime.now(UTC)),
                filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED,)),
            )
            if changed == 0:
                raise ConflictError("Job run is no longer queued")
            await repos.jobs.heartbeat_run(run_id)

            # Persist queued batches before dispatch so interrupted work remains visible to recovery.
            if batches:
                await repos.jobs.upsert_batches([
                    JobBatchCreate(
                        run_id=run_id,
                        batch_no=b.batch_no,
                        offset=b.offset,
                        batch_size=b.batch_size,
                        status=JobBatchStatus.QUEUED
                    ) for b in batches
                ])

        try:
            semaphore = asyncio.Semaphore(max_concurrent_batches)

            async def guarded(b: JobBatchParams) -> JobBatchResult | JobFailedBatch:
                async with semaphore:
                    return await self._run_batch(run_id=run_id, batch=b)

            tasks = [asyncio.create_task(guarded(batch)) for batch in batches]
            try:
                results = await asyncio.gather(*tasks)
            except BaseException:
                # gather can raise while siblings still write. Drain them before releasing the run.
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

            successful = [r for r in results if isinstance(r, JobBatchResult)]
            failed = [r for r in results if isinstance(r, JobFailedBatch)]

            total_processed = sum(r.processed_count for r in successful)
            status = self._final_status(success_count=len(successful), failure_count=len(failed))

            # Audit failure is recorded in metadata but never changes the batch-derived status.
            audit, audit_error = await self._audit_safely()

            final_metadata = {
                "batch_size": batch_size,
                "max_concurrent_batches": max_concurrent_batches,
                "total_rows": total_rows,
                "total_batches": len(batches),
                "total_processed": total_processed,
                "metadata": metadata,
                JobRunMetadataKey.AUDIT: audit,
                "audit_error": audit_error,
            }

            async with self.app_db.start() as repos:
                await repos.jobs.update_runs(
                    update_model=JobRunUpdate(status=status, metadata_json=final_metadata, finished_at=datetime.now(UTC)),
                    filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED, JobStatus.RUNNING)),
                )

            return JobRunResult(
                job_name=self.job_name,
                run_id=run_id,
                mode=mode,
                status=status,
                batch_size=batch_size,
                max_concurrent_batches=max_concurrent_batches,
                total_rows=total_rows,
                total_batches=len(batches),
                total_processed=total_processed,
                failed_batches=failed,
                audit=audit,
                audit_error=audit_error,
                metadata=metadata,
            )

        # Batch errors are handled in _run_batch; reaching here means batch-state or final-state
        # persistence failed. Mark the run FAILED now instead of leaving it RUNNING.
        except Exception as exc:
            await self._fail_run(run_id=run_id, exc=exc, metadata=metadata)
            raise


    async def _run_batch(
            self,
            *,
            run_id: int,
            batch: JobBatchParams,
    ) -> JobBatchResult | JobFailedBatch:
        try:
            async with self.app_db.start() as repos:
                changed = await repos.jobs.update_batches(
                    update_model=JobBatchUpdate(
                        status=JobBatchStatus.RUNNING, error_type=None, error_message=None, started_at=datetime.now(UTC)
                    ),
                    filters=JobBatchFilter(run_id=run_id, batch_no=batch.batch_no, statuses=(JobBatchStatus.QUEUED,)),
                )
                if changed == 0:
                    raise ConflictError("Job batch is no longer queued")

            result = await self.executor.execute_batch(batch)

            async with self.app_db.start() as repos:
                await repos.jobs.update_batches(
                    update_model=JobBatchUpdate(
                        status=JobBatchStatus.SUCCESS, processed_count=result.processed_count, metadata_json=result.metadata,
                        error_type=None, error_message=None, finished_at=datetime.now(UTC)
                    ),
                    filters=JobBatchFilter(run_id=run_id, batch_no=batch.batch_no, statuses=(JobBatchStatus.RUNNING,)),
                )

            return result

        # Treat executor and batch-state errors alike; record FAILED and return a retryable
        # result when persistence succeeds.
        except Exception as exc:
            failed = JobFailedBatch(
                batch_no=batch.batch_no,
                offset=batch.offset,
                batch_size=batch.batch_size,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )

            logger.warning(
                "job_batch_failed",
                job=self.job_name,
                run_id=run_id,
                batch_no=batch.batch_no,
                offset=batch.offset,
                batch_size=batch.batch_size,
                error_type=failed.error_type,
                error_message=failed.error_message,
            )

            async with self.app_db.start() as repos:
                await repos.jobs.update_batches(
                    update_model=JobBatchUpdate(
                        status=JobBatchStatus.FAILED, error_type=failed.error_type,
                        error_message=failed.error_message[:ERROR_MESSAGE_MAX_CHARS], finished_at=datetime.now(UTC)
                    ),
                    filters=JobBatchFilter(run_id=run_id, batch_no=batch.batch_no, statuses=(JobBatchStatus.RUNNING,)),
                )

            return failed

    async def _plan_batches(
            self,
            *,
            batch_size: int,
            mode: JobMode,
    ) -> tuple[int, list[JobBatchParams]]:
        # RETRY replays only the FAILED batches of the most recent eligible FAILED/PARTIAL_SUCCESS
        # run, reusing their offsets under the new run_id.
        if mode is JobMode.RETRY:
            async with self.app_db.start() as repos:
                runs = await repos.jobs.fetch_runs(
                    page_params=JobRunPageParams(
                        limit=1,
                        order_by=[SortSpec(field=JobRunSortField.CREATED_AT, direction=SortDirection.DESC)]
                    ),
                    filters=JobRunFilter(
                        job_name=self.job_name,
                        statuses=(JobStatus.FAILED, JobStatus.PARTIAL_SUCCESS),
                    )
                )

                if not runs:
                    return 0, []

                failed_batches = await repos.jobs.fetch_batches(
                    page_params=JobBatchPageParams(
                        limit=MAX_RETRY_BATCHES,
                        order_by=[SortSpec(field=JobBatchSortField.BATCH_NO, direction=SortDirection.ASC)]
                    ),
                    filters=JobBatchFilter(
                        run_id=runs[0].id,
                        status=JobBatchStatus.FAILED,
                    )
                )

            batches = [
                JobBatchParams(
                    batch_no=batch.batch_no,
                    offset=batch.offset,
                    batch_size=batch.batch_size,
                )
                for batch in failed_batches
            ]

            return sum(batch.batch_size for batch in batches), batches

        # Offsets come from a single count; rows added or removed mid-run can shift batch boundaries.
        total_rows = await self.executor.count_total()

        return total_rows, [
            JobBatchParams(
                batch_no=batch_no,
                offset=offset,
                batch_size=batch_size,
            )
            for batch_no, offset in enumerate(range(0, total_rows, batch_size), start=1)
        ]

    async def _fail_run(self, *, run_id: int, exc: Exception, metadata: dict | None) -> None:
        """Best effort: record the run as FAILED. The caller re-raises the original error either way."""
        error = error_details(exc)
        logger.error("job_run_failed", job=self.job_name, run_id=run_id, **error)
        try:
            async with self.app_db.start() as repos:
                await repos.jobs.update_runs(
                    update_model=JobRunUpdate(
                        status=JobStatus.FAILED, metadata_json={"metadata": metadata, "error": error},
                        finished_at=datetime.now(UTC),
                    ),
                    filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED, JobStatus.RUNNING)),
                )
        except Exception as persist_exc:
            # The database is likely the cause; the run stays RUNNING (see the module docstring).
            logger.warning("job_run_failure_not_persisted", job=self.job_name, run_id=run_id, **error_details(persist_exc))

    async def _audit_safely(self) -> tuple[dict | None, dict | None]:
        """Run the auditor; its failure is reported next to the result instead of failing the run."""
        if self.auditor is None:
            return None, None

        try:
            return await self.auditor.run_audit(), None
        except Exception as exc:
            return None, {
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            }

    async def _complete_empty_retry(
            self,
            *,
            run_id: int,
            batch_size: int,
            max_concurrent_batches: int,
            metadata: dict | None,
    ) -> JobRunResult:
        final_metadata = {
            "batch_size": batch_size,
            "max_concurrent_batches": max_concurrent_batches,
            "total_rows": 0,
            "total_batches": 0,
            "total_processed": 0,
            "metadata": metadata,
            "message": "No failed batches found for retry.",
        }

        async with self.app_db.start() as repos:
            await repos.jobs.update_runs(
                update_model=JobRunUpdate(status=JobStatus.SUCCESS, metadata_json=final_metadata, finished_at=datetime.now(UTC)),
                filters=JobRunFilter(id=run_id, statuses=(JobStatus.QUEUED, JobStatus.RUNNING)),
            )

        return JobRunResult(
            job_name=self.job_name,
            run_id=run_id,
            mode=JobMode.RETRY,
            status=JobStatus.SUCCESS,
            batch_size=batch_size,
            max_concurrent_batches=max_concurrent_batches,
            total_rows=0,
            total_batches=0,
            total_processed=0,
            metadata=metadata,
            message="No failed batches found for retry.",
        )

    @staticmethod
    def _final_status(
            *,
            success_count: int,
            failure_count: int,
    ) -> JobStatus:
        if failure_count and success_count:
            return JobStatus.PARTIAL_SUCCESS

        if failure_count:
            return JobStatus.FAILED

        return JobStatus.SUCCESS

    @staticmethod
    def _validate(batch_size: int, max_concurrent_batches: int) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")

        if max_concurrent_batches <= 0:
            raise ValueError("max_concurrent_batches must be greater than 0")

        if max_concurrent_batches > MAX_CONCURRENT_BATCHES:
            raise ValueError(f"max_concurrent_batches must be <= {MAX_CONCURRENT_BATCHES}")
