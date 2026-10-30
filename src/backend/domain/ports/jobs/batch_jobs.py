"""Contracts a batch job implements (executor, auditor) and the launcher that starts runs."""
from collections.abc import Awaitable, Callable
from typing import Protocol

from backend.domain.entities.jobs import JobBatchParams, JobBatchResult


class BatchExecutor(Protocol):
    async def count_total(self) -> int:
        ...

    async def execute_batch(self, batch: JobBatchParams) -> JobBatchResult:
        ...


class BatchAuditor(Protocol):
    async def run_audit(self) -> dict:
        ...


class JobLauncher(Protocol):
    """Runs a recorded job outside the request that started it.

    `work` executes the job for `run_id` and records its progress and outcome on that run. The launcher
    keeps the run's heartbeat alive while it works, and marks the run FAILED if `work` ends without
    doing so (crash, shutdown), so a run never stays QUEUED or RUNNING forever.
    """
    async def launch(self, run_id: int, work: Callable[[], Awaitable[object]]) -> None:
        ...