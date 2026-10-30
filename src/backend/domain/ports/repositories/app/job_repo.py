"""Job run/batch repository port, including heartbeats used to detect abandoned runs."""
from typing import Protocol

from pydantic import BaseModel

from backend.domain.entities.jobs import (
    JobBatchCreate,
    JobBatchRead,
    JobBatchUpdate,
    JobRunCreate,
    JobRunRead,
    JobRunUpdate,
)
from backend.domain.ports.repositories.app.query_types import (
    JobBatchPageParams,
    JobRunPageParams,
)
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter
from backend.domain.ports.repositories.types import PrimaryKey


class JobRepository(Protocol):
    async def lock_submission(self, job_name: str) -> None:
        """Serialize submissions for this name until the current transaction ends."""
        ...

    # Runs (Append-Only)
    async def create_run(self, payload: JobRunCreate) -> int: ...
    async def update_runs(self, update_model: JobRunUpdate, filters: JobRunFilter | None = None) -> int: ...
    async def fetch_runs[T: BaseModel = JobRunRead](
            self,
            page_params: JobRunPageParams,
            filters: JobRunFilter | None = None,
            *,
            view_model: type[T] = JobRunRead,
    ) -> list[T]: ...

    async def upsert_batches(self, payloads: list[JobBatchCreate]) -> list[PrimaryKey]: ...
    async def update_batches(self, update_model: JobBatchUpdate, filters: JobBatchFilter | None = None) -> int: ...
    async def fetch_batches[T: BaseModel = JobBatchRead](
            self,
            page_params: JobBatchPageParams,
            filters: JobBatchFilter | None = None,
            *,
            view_model: type[T] = JobBatchRead,
    ) -> list[T]: ...

    # Zombie Jobs (for cleanup)
    async def heartbeat_run(self, run_id: int) -> None: ...
    async def fail_zombie_jobs(self, timeout_minutes: int = 5) -> int: ...
