"""Contracts a batch job implements (executor, auditor) and the launcher that starts runs."""
from typing import Protocol

from backend.domain.entities.job_requests import JobRequest
from backend.domain.entities.jobs import (
    JobBatchParams,
    JobBatchResult,
    JobFailureReason,
)


class BatchExecutor(Protocol):
    async def count_total(self) -> int:
        ...

    async def execute_batch(self, batch: JobBatchParams) -> JobBatchResult:
        ...


class BatchAuditor(Protocol):
    async def run_audit(self) -> dict:
        ...


class JobRunExecutor(Protocol):
    """Runs one recorded job to a final run status (application: JobExecution).

    Launchers and workers (infra) depend on this contract, not on the application class.
    """
    async def run(self, run_id: int, request: JobRequest) -> None:
        """Run the job; re-raises only cancellation."""
        ...

    async def run_stored(self, run_id: int) -> None:
        """Run the request stored on the run (workers receive only the run id); re-raises only cancellation."""
        ...

    async def fail_if_unfinished(self, run_id: int, reason: JobFailureReason) -> None:
        """Mark the run FAILED unless it already reached a final status."""
        ...


class JobLauncher(Protocol):
    """Starts a recorded run outside the request that submitted it, and returns without waiting.

    `request` is the job's data (also stored on the run), so an implementation may run it in this
    process or hand it to another. Whoever runs it keeps the run's heartbeat alive and marks the run
    FAILED if the job ends without recording an outcome, so a run never stays QUEUED or RUNNING forever.
    """
    async def launch(self, run_id: int, request: JobRequest) -> None:
        ...