"""Run jobs as asyncio tasks in this API process (system.jobs.execution: in_process, development only;
staging and production use worker containers, docs/backend/architecture.md#background-jobs).

This adapter is not a durable queue: restarts end work, and failed work must be resubmitted. Running a
job (heartbeat, failure rules) is the JobRunExecutor's; this class only owns the tasks and their shutdown.
"""

from __future__ import annotations

import asyncio

import structlog

from backend.domain.entities.job_requests import JobRequest
from backend.domain.entities.jobs import JobFailureReason
from backend.domain.errors import DependencyUnavailableError
from backend.domain.ports.jobs.batch_jobs import JobRunExecutor

logger = structlog.get_logger(__name__)


class InProcessJobLauncher:
    def __init__(self, execution: JobRunExecutor) -> None:
        self.execution = execution
        self._tasks: dict[asyncio.Task[None], int] = {}
        self._closed = False

    async def launch(self, run_id: int, request: JobRequest) -> None:
        if self._closed:
            raise DependencyUnavailableError("Job execution is shutting down")
        task = asyncio.create_task(self.execution.run(run_id, request), name=f"job-run-{run_id}")
        self._tasks[task] = run_id
        task.add_done_callback(self._finished)
        logger.info("job_launched", run_id=run_id, job=request.key.value)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.pop(task, None)
        if not task.cancelled() and task.exception() is not None:
            logger.error("job_launcher_failed", task=task.get_name(), exc_info=task.exception())

    async def shutdown(self) -> None:
        """Cancel and await work, including jobs cancelled before their first instruction."""
        self._closed = True
        tasks = dict(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # A task cancelled before it started never ran JobExecution's own cancellation handling.
        for run_id in tasks.values():
            await self.execution.fail_if_unfinished(run_id, JobFailureReason.INTERRUPTED)
