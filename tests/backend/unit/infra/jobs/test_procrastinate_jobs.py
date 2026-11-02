"""Worker execution through Procrastinate: the API defers `run_job(run_id)` on the job's queue, and a
worker runs it through the JobRunExecutor.

Uses Procrastinate's InMemoryConnector, so no Postgres or psycopg event loop is needed (runs on Windows).
"""
from procrastinate import App
from procrastinate.testing import InMemoryConnector

from backend.domain.entities.job_requests import (
    IndexingParams,
    JobKey,
    JobQueue,
    WebsiteCrawlParams,
)
from backend.domain.entities.jobs import JobMode
from backend.domain.settings.scraping import Website
from backend.infra.jobs.procrastinate_app import (
    RETRY_STALLED_JOBS_TASK,
    RUN_JOB_TASK,
    STALLED_JOB_RETRY_CRON,
    register_worker_tasks,
)
from backend.infra.jobs.procrastinate_launcher import ProcrastinateJobLauncher

CRAWL = WebsiteCrawlParams(site=Website.WLU, mode=JobMode.UPDATE, page_limit=None, concurrency=4, timeout_seconds=30)
INDEXING = IndexingParams(key=JobKey.PAGE_INDEXING, mode=JobMode.UPDATE, batch_size=50, max_concurrent_batches=1)


class RecordingExecutor:
    def __init__(self):
        self.ran: list[int] = []

    async def run(self, run_id, request):
        raise AssertionError("workers run the stored request, never one passed in memory")

    async def run_stored(self, run_id):
        self.ran.append(run_id)

    async def fail_if_unfinished(self, run_id, reason):
        raise AssertionError("not expected")


async def test_launcher_queues_only_the_run_id_on_the_jobs_queue():
    connector = InMemoryConnector()
    app = App(connector=connector)

    async with app.open_async():
        launcher = ProcrastinateJobLauncher(app)
        await launcher.launch(7, CRAWL)
        await launcher.launch(8, INDEXING)

    jobs = sorted(connector.jobs.values(), key=lambda job: job["id"])
    assert [(job["task_name"], job["queue_name"], job["args"]) for job in jobs] == [
        (RUN_JOB_TASK, JobQueue.INGESTION.value, {"run_id": 7}),
        (RUN_JOB_TASK, JobQueue.INDEXING.value, {"run_id": 8}),
    ]


async def test_a_worker_runs_each_queued_run_through_the_executor():
    connector = InMemoryConnector()
    executor = RecordingExecutor()
    # The API defers by name on an App without tasks; the worker registers the task.
    api_app = App(connector=connector)
    worker_app = register_worker_tasks(App(connector=connector), executor)

    async with api_app.open_async():
        await ProcrastinateJobLauncher(api_app).launch(7, CRAWL)
        await ProcrastinateJobLauncher(api_app).launch(8, INDEXING)
    async with worker_app.open_async():
        # wait=False: process what is queued, then return.
        await worker_app.run_worker_async(
            queues=[queue.value for queue in JobQueue], wait=False, install_signal_handlers=False,
        )

    assert sorted(executor.ran) == [7, 8]
    assert {job["status"] for job in connector.jobs.values()} == {"succeeded"}


def test_the_worker_retries_stalled_jobs_periodically_on_the_maintenance_queue():
    app = register_worker_tasks(App(connector=InMemoryConnector()), RecordingExecutor())

    task = app.tasks[RETRY_STALLED_JOBS_TASK]
    assert task.queue == JobQueue.MAINTENANCE.value
    assert task.queueing_lock == RETRY_STALLED_JOBS_TASK  # Never two cleanups queued at once.
    [periodic] = [p for p in app.periodic_registry.periodic_tasks.values() if p.task is task]
    assert periodic.cron == STALLED_JOB_RETRY_CRON
