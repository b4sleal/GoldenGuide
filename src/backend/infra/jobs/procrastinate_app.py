"""Procrastinate (Postgres-backed job queue) for worker execution (docs/backend/architecture.md#background-jobs).

Procrastinate only delivers work: it queues `run_job(run_id)` and a worker claims and runs it. What
the job is and how it went live in `job_runs` (our business record), so a single generic task is
enough: it reads the run's stored request and runs it through the JobRunExecutor.

The App is built in this importable module, not in a `__main__` script, as Procrastinate recommends.
It uses psycopg 3 (`PsycopgConnector`, required for async workers); SQLAlchemy keeps asyncpg.
"""
from __future__ import annotations

import structlog
from procrastinate import App, PsycopgConnector
from psycopg.conninfo import make_conninfo

from backend.domain.entities.job_requests import JobQueue
from backend.domain.ports.jobs.batch_jobs import JobRunExecutor
from backend.domain.settings.jobs import WorkerSettings
from backend.domain.settings.providers import DBSettings

logger = structlog.get_logger(__name__)

# Task names are stored with queued jobs: changing one strands jobs already queued under the old name,
# so treat them like schema names. RUN_JOB_TASK is shared by the launcher (defers it) and the worker.
RUN_JOB_TASK = "goldenguide.run_job"
RETRY_STALLED_JOBS_TASK = "goldenguide.retry_stalled_jobs"
# Every 10 minutes, as in Procrastinate's "Retry stalled jobs" guide.
STALLED_JOB_RETRY_CRON = "*/10 * * * *"


def build_procrastinate_app(db: DBSettings, worker: WorkerSettings) -> App:
    """An App on the application database. Not opened: callers open and close it (API lifespan, worker)."""
    # make_conninfo quotes every value, so special characters in the password are safe.
    conninfo = make_conninfo(
        host=db.host,
        port=db.port,
        user=db.user.get_secret_value(),
        password=db.password.get_secret_value(),
        dbname=db.database,
    )
    # Extra arguments go to psycopg_pool.AsyncConnectionPool. min_size=1 keeps any configured
    # max_size valid (the pool's default min_size is 4).
    return App(connector=PsycopgConnector(conninfo=conninfo, min_size=1, max_size=worker.db_pool_max_size))


def register_worker_tasks(app: App, executor: JobRunExecutor) -> App:
    """Register the tasks a worker runs. Only the worker needs this; the API only defers by name."""

    @app.task(name=RUN_JOB_TASK)
    async def run_job(run_id: int) -> None:
        """Run one recorded job. Failures are recorded on its run by the executor, never raised here,
        so Procrastinate's own job status only says "delivered", not whether the job succeeded."""
        await executor.run_stored(run_id)

    # Procrastinate's documented pattern for workers that died mid-job ("Retry stalled jobs"): their
    # `doing` jobs are re-queued. Re-delivering run_job never runs a job twice: by then its run is
    # RUNNING or already FAILED by the zombie sweep, not QUEUED, so JobExecution skips it. The retry
    # only closes the queue's record; whether to resubmit the job stays the operator's decision.
    @app.periodic(cron=STALLED_JOB_RETRY_CRON)
    @app.task(name=RETRY_STALLED_JOBS_TASK, queue=JobQueue.MAINTENANCE.value, queueing_lock=RETRY_STALLED_JOBS_TASK)
    async def retry_stalled_jobs(timestamp: int) -> None:
        stalled = await app.job_manager.get_stalled_jobs(task_name=RUN_JOB_TASK)
        for job in stalled:
            await app.job_manager.retry_job(job)
            logger.warning("queue_stalled_job_retried", queue_job_id=job.id, args=job.task_kwargs)

    return app
