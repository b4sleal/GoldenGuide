"""JobLauncher that queues runs for worker containers (system.jobs.execution: worker)."""
from __future__ import annotations

import structlog
from procrastinate import App

from backend.domain.entities.job_requests import JobRequest, job_queue
from backend.infra.jobs.procrastinate_app import RUN_JOB_TASK

logger = structlog.get_logger(__name__)


class ProcrastinateJobLauncher:
    """Defers `run_job(run_id)` on the job's queue; a worker runs it. The request itself stays on the run."""

    def __init__(self, app: App) -> None:
        self.app = app

    async def launch(self, run_id: int, request: JobRequest) -> None:
        queue = job_queue(request.key)
        # By name: the API process never registers worker tasks (procrastinate_app.py).
        task = self.app.configure_task(name=RUN_JOB_TASK, queue=queue.value, allow_unknown=True)
        job_id = await task.defer_async(run_id=run_id)
        logger.info("job_queued", run_id=run_id, job=request.key.value, queue=queue.value, queue_job_id=job_id)

    async def shutdown(self) -> None:
        """Nothing to stop: queued work belongs to the workers, and survives an API restart."""
