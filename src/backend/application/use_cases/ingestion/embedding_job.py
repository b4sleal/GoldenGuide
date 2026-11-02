"""Embedding as a tracked batch job: fresh embeds every record, update only flagged ones, retry re-runs
the failed batches of the last run.

Batches page through the whole table in id order and the needs_embedding check happens here, not in
SQL, so a batch's offset always covers the same rows: retry replays exactly what failed even after
other batches cleared their flags. One record failing never stops the rest of its batch; the batch
then fails listing those records, which stay flagged so retry and update pick them up.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import structlog

from backend.application.services.jobs.job_runner import BatchJobRunner
from backend.application.use_cases.ingestion.ingest_knowledge import KnowledgeIngestor
from backend.domain.entities.ingestion_types import KnowledgeVectorPayload, VectorSource
from backend.domain.entities.jobs import JobBatchParams, JobBatchResult, JobMode, JobStatus
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.ports.repositories.types import PrimaryKey

logger = structlog.get_logger()


class EmbeddingSource[R](Protocol):
    """One table whose records are embedded: how to page it, build payloads and flag records."""
    name: VectorSource

    async def count(self, repos) -> int: ...

    async def fetch(self, repos, offset: int, limit: int) -> list[R]: ...

    def record_id(self, record: R) -> PrimaryKey: ...

    def needs_embedding(self, record: R) -> bool: ...

    def payload(self, record: R) -> KnowledgeVectorPayload: ...

    async def set_needs_embedding(self, repos, ids: list[PrimaryKey], value: bool) -> None: ...


class EmbeddingBatchError(RuntimeError):
    """Some records in a batch could not be embedded; the rest of the batch was."""

    def __init__(self, source_ids: list[str], errors: list[str]):
        self.source_ids = source_ids
        super().__init__(f"{len(source_ids)} record(s) failed to embed: " + "; ".join(errors))


class EmbeddingJob:
    JOB_NAME = "embedding"

    def __init__(self, app_db: AppDB, school_db: SchoolDB, knowledge_service: KnowledgeIngestor, source: EmbeddingSource):
        self.app_db = app_db
        self.school_db = school_db
        self.knowledge_service = knowledge_service
        self.source = source

    @classmethod
    def job_name_for(cls, source: VectorSource) -> str:
        """The run name (and duplicate-run lock key) of the embedding job for `source`."""
        return f"{cls.JOB_NAME}:{source.value}"

    @property
    def job_name(self) -> str:
        return self.job_name_for(self.source.name)

    async def run(self, *, run_id: int, mode: JobMode, batch_size: int, max_concurrent_batches: int) -> dict:
        started_at = datetime.now(timezone.utc)
        executor = EmbeddingExecutor(self.school_db, self.knowledge_service, self.source, mode)
        runner = BatchJobRunner(
            app_db=self.app_db,
            job_name=self.job_name,
            executor=executor,
        )
        result = await runner.execute(
            run_id=run_id,
            batch_size=batch_size,
            max_concurrent_batches=max_concurrent_batches,
            mode=mode,
            metadata={"source": self.source.name.value},
        )
        output = result.model_dump(mode="json")
        logger.info(
            "embedding_job_finished",
            source=self.source.name.value,
            run_id=run_id,
            mode=mode.value,
            status=result.status.value,
            records_total=result.total_rows,
            records_embedded=executor.embedded_total,
            records_failed=executor.failed_total,
            failed_batches=len(result.failed_batches),
            duration_seconds=round((datetime.now(timezone.utc) - started_at).total_seconds(), 1),
        )

        # A fully successful fresh run re-embedded every record, so any of this source's vectors it did
        # not touch belong to records that no longer exist (deleted or re-imported under a new id).
        # A run with failures sweeps nothing: an untouched vector may be a record that failed.
        if mode is JobMode.FRESH and result.status == JobStatus.SUCCESS:
            output["stale_vectors_deleted"] = await self.knowledge_service.delete_stale(self.source.name, started_at)
        return output


class EmbeddingExecutor:
    """Embeds one batch of records; keeps running totals so progress can be logged across batches."""

    def __init__(self, school_db: SchoolDB, knowledge_service: KnowledgeIngestor, source: EmbeddingSource, mode: JobMode):
        self.school_db = school_db
        self.knowledge_service = knowledge_service
        self.source = source
        self.mode = mode
        # Batches run concurrently on one event loop, so plain counters are safe (no await between updates).
        self.records_total: int | None = None
        self.records_done = 0
        self.embedded_total = 0
        self.failed_total = 0

    async def count_total(self) -> int:
        async with self.school_db.start() as repos:
            self.records_total = await self.source.count(repos)
            return self.records_total

    def _log_progress(self, batch: JobBatchParams, fetched: int, embedded: int, failed: int) -> None:
        self.records_done += fetched
        self.embedded_total += embedded
        self.failed_total += failed
        logger.info(
            "embedding_batch_finished",
            source=self.source.name.value,
            batch_no=batch.batch_no,
            batch_embedded=embedded,
            batch_failed=failed,
            embedded_so_far=self.embedded_total,
            failed_so_far=self.failed_total,
            # RETRY never counts the table, so there is no total to show progress against.
            progress=f"{self.records_done}/{self.records_total}" if self.records_total else None,
        )

    async def execute_batch(self, batch: JobBatchParams) -> JobBatchResult:
        async with self.school_db.start() as repos:
            records = await self.source.fetch(repos, offset=batch.offset, limit=batch.batch_size)

        # Fresh embeds every record; update and retry only those still flagged.
        pending = records if self.mode is JobMode.FRESH else [r for r in records if self.source.needs_embedding(r)]

        embedded: list[PrimaryKey] = []
        failed: list[PrimaryKey] = []
        failed_source_ids: list[str] = []
        errors: list[str] = []

        for record in pending:
            payload = self.source.payload(record)
            try:
                await self.knowledge_service.ingest(payload)
            except Exception as exc:
                logger.warning(
                    "embedding_record_failed",
                    source=self.source.name,
                    source_id=payload.source_id,
                    error_type=exc.__class__.__name__,
                    error=str(exc),
                )
                failed.append(self.source.record_id(record))
                failed_source_ids.append(payload.source_id)
                errors.append(f"{payload.source_id}: {exc.__class__.__name__}: {exc}")
                continue
            embedded.append(self.source.record_id(record))

        async with self.school_db.start() as repos:
            if embedded:
                await self.source.set_needs_embedding(repos, embedded, False)
            # A fresh run may fail a record that was not flagged: flag it so retry and update find it.
            if failed:
                await self.source.set_needs_embedding(repos, failed, True)

        self._log_progress(batch, fetched=len(records), embedded=len(embedded), failed=len(failed))

        if failed:
            raise EmbeddingBatchError(failed_source_ids, errors)

        return JobBatchResult(
            processed_count=len(records),
            metadata={
                "source": self.source.name,
                "records_fetched": len(records),
                "records_embedded": len(embedded),
                "records_unchanged": len(records) - len(pending),
            },
        )
