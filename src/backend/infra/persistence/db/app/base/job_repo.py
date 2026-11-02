"""SQL job repository: runs, batches, heartbeats, and failing runs whose heartbeat stopped."""
from datetime import UTC, datetime, timedelta
from typing import cast

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.entities.jobs import (
    JobBatchBase,
    JobBatchCreate,
    JobBatchField,
    JobBatchRead,
    JobBatchStatus,
    JobBatchUpdate,
    JobRunCreate,
    JobRunField,
    JobRunRead,
    JobRunUpdate,
    JobStatus,
)
from backend.domain.ports.repositories.app.query_types import (
    JobBatchPageParams,
    JobRunPageParams,
)
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter
from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.app.app_tables import JobBatch, JobRun
from backend.infra.persistence.db.app.filters import (
    JobBatchFilterTranslator,
    JobRunFilterTranslator,
)
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.utils.generic.db_ops import (
    extract_payload,
    generic_fetch,
)
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting
from backend.infra.persistence.db.utils.generic.update_rules import overwrite
from backend.infra.persistence.db.utils.generic.upsert_mapping import (
    column_name,
    mapped_table,
    prepare_rows,
    update_columns,
)


class SqlJobRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps) -> None:
        self.session = session
        self.dialect = dialect
        self.aliases: dict[str, InstrumentedAttribute] = {}

    # ==========================================
    # RUNS
    # ==========================================
    async def lock_submission(self, job_name: str) -> None:
        await self.dialect.lock_transaction(self.session, f"job-submission:{job_name}")

    async def create_run(self, payload: JobRunCreate) -> int:
        safe_payload = extract_payload(payload, self.aliases)
        row = JobRun(**safe_payload)

        self.session.add(row)
        await self.session.flush()
        return row.id

    async def update_runs(self, update_model: JobRunUpdate, filters: JobRunFilter | None = None) -> int:
        id_stmt = JobRunFilterTranslator.apply(select(JobRun.id), filters)
        stmt = update(JobRun).where(JobRun.id.in_(id_stmt))
        if filters is not None and filters.statuses is not None:
            stmt = stmt.where(JobRun.status.in_(filters.statuses))

        # Pydantic explicitly tracks what was set vs left out. No magic command flags needed.
        patch = extract_payload(update_model, self.aliases, exclude_unset=True)
        if not patch: return 0

        result = await self.session.execute(stmt.values(**patch))
        await self.session.flush()
        return cast(CursorResult, result).rowcount or 0

    async def fetch_runs[T: BaseModel = JobRunRead](
            self,
            page_params: JobRunPageParams,
            filters: JobRunFilter | None = None,
            *,
            view_model: type[T] = JobRunRead,
    ) -> list[T]:
        stmt = select(JobRun)
        stmt = JobRunFilterTranslator.apply(stmt, filters)
        stmt = apply_sorting(
            stmt=stmt, model=JobRun, order_by=page_params.order_by,
            aliases=self.aliases, stable_tiebreaker=JobRunField.ID.value
        )
        return await generic_fetch(self.session, stmt, JobRun, view_model, page_params, self.aliases)

    # ==========================================
    # BATCHES
    # ==========================================
    async def upsert_batches(self, payloads: list[JobBatchCreate]) -> list[PrimaryKey]:
        identity = JobBatchBase.IDENTITY_FIELDS
        columns = update_columns(JobBatchUpdate, identity_fields=identity, aliases=self.aliases)

        return await self.dialect.upsert(
            self.session,
            table=mapped_table(JobBatch),
            rows=prepare_rows(payloads, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
            build_updates=lambda existing, incoming: overwrite(incoming, columns),
        )

    async def update_batches(self, update_model: JobBatchUpdate, filters: JobBatchFilter | None = None) -> int:
        id_stmt = JobBatchFilterTranslator.apply(select(JobBatch.id), filters)
        stmt = update(JobBatch).where(JobBatch.id.in_(id_stmt))
        if filters is not None and filters.statuses is not None:
            stmt = stmt.where(JobBatch.status.in_(filters.statuses))

        # Pure state transfer.
        patch = extract_payload(update_model, self.aliases, exclude_unset=True)
        if not patch: return 0

        result = await self.session.execute(stmt.values(**patch))
        await self.session.flush()
        return cast(CursorResult, result).rowcount or 0

    async def fetch_batches[T: BaseModel = JobBatchRead](
            self,
            page_params: JobBatchPageParams,
            filters: JobBatchFilter | None = None,
            *,
            view_model: type[T] = JobBatchRead,
    ) -> list[T]:
        stmt = select(JobBatch)
        stmt = JobBatchFilterTranslator.apply(stmt, filters)
        stmt = apply_sorting(
            stmt=stmt, model=JobBatch, order_by=page_params.order_by,
            aliases=self.aliases, stable_tiebreaker=JobBatchField.ID.value
        )
        return await generic_fetch(self.session, stmt, JobBatch, view_model, page_params, self.aliases)

    async def heartbeat_run(self, run_id: int) -> None:
        """Lightweight ping to keep the job alive in a distributed fleet."""
        stmt = update(JobRun).where(JobRun.id == run_id).values(last_heartbeat_at=func.now())
        await self.session.execute(stmt)
        await self.session.flush()

    async def fail_zombie_jobs(self, *, heartbeat_timeout_minutes: int, queued_timeout_minutes: int) -> int:
        """Fail unfinished runs that can no longer finish.

        - RUNNING: no heartbeat (or, before the first one, no start) within `heartbeat_timeout_minutes`;
          the process running it died.
        - QUEUED: waiting longer than `queued_timeout_minutes`. Runs legitimately wait in a worker queue
          behind other jobs, so this limit is much longer; it still catches a run recorded by a process
          that died before queueing it, which would otherwise block new runs of that job forever.
        """
        now = datetime.now(UTC)
        heartbeat_cutoff = now - timedelta(minutes=heartbeat_timeout_minutes)
        queued_cutoff = now - timedelta(minutes=queued_timeout_minutes)

        # Claim stale runs atomically: concurrent heartbeats/completions recheck this predicate.
        dead_runs_stmt = update(JobRun).where(
            or_(
                and_(
                    JobRun.status == JobStatus.RUNNING,
                    func.coalesce(JobRun.last_heartbeat_at, JobRun.created_at) < heartbeat_cutoff,
                ),
                and_(JobRun.status == JobStatus.QUEUED, JobRun.created_at < queued_cutoff),
            ),
        ).values(status=JobStatus.FAILED, finished_at=func.now()).returning(JobRun.id)

        result = await self.session.execute(dead_runs_stmt)
        dead_run_ids = result.scalars().all()

        if not dead_run_ids:
            return 0

        # 2. Kill their stranded batches
        await self.session.execute(
            update(JobBatch)
            .where(JobBatch.run_id.in_(dead_run_ids))
            .where(JobBatch.status.in_([JobBatchStatus.RUNNING, JobBatchStatus.QUEUED]))
            .values(
                status=JobBatchStatus.FAILED,
                error_type="HeartbeatTimeout",
                error_message=(
                    f"No heartbeat for >{heartbeat_timeout_minutes} minutes, "
                    f"or queued for >{queued_timeout_minutes} minutes."
                ),
                finished_at=func.now()
            )
        )

        await self.session.flush()
        return len(dead_run_ids)
