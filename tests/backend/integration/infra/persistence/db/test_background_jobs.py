"""Real PostgreSQL transactions verify replica exclusion and race-safe stale-run recovery."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.application.services.jobs.job_submit import JobSubmissionService
from backend.domain.entities.job_requests import RegistrationImportParams
from backend.domain.entities.jobs import (
    JobBatchCreate,
    JobBatchStatus,
    JobMode,
    JobRunCreate,
    JobRunUpdate,
    JobStatus,
)
from backend.domain.errors import ConflictError
from backend.domain.ports.repositories.app.query_types import (
    JobBatchPageParams,
    JobRunPageParams,
)
from backend.domain.ports.repositories.filters import JobBatchFilter, JobRunFilter
from backend.infra.persistence.db.app.app_tables import AppBaseTable, JobRun
from backend.infra.persistence.db.app.base.job_repo import SqlJobRepository
from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps

REQUEST = RegistrationImportParams(term_code="202609")


@pytest.fixture
async def db(test_database_url):
    # A unique schema prevents interference with any other tests in the disposable DB.
    schema = f"jobs_review_{uuid4().hex}"
    engine = create_async_engine(
        test_database_url, execution_options={"schema_translate_map": {None: schema}}
    )
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.run_sync(AppBaseTable.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def start():
        async with sessions.begin() as session:
            yield SimpleNamespace(
                jobs=SqlJobRepository(session, PostgresDialectOps()), session=session
            )

    try:
        yield SimpleNamespace(start=start)
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


async def test_two_independent_submission_services_cannot_start_the_same_job(db):
    launcher = SimpleNamespace(launch=AsyncMock())
    services = [JobSubmissionService(db, launcher), JobSubmissionService(db, launcher)]
    results = await asyncio.gather(
        *(
            service.submit(
                job_name="crawl:wlu", mode=JobMode.UPDATE, request=REQUEST
            )
            for service in services
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ConflictError) for result in results) == 1
    assert launcher.launch.await_count == 1
    async with db.start() as repos:
        runs = await repos.jobs.fetch_runs(JobRunPageParams())
    assert len(runs) == 1


async def test_sweep_fails_only_stale_unfinished_runs_and_their_unfinished_batches(db):
    stale = datetime.now(UTC) - timedelta(minutes=10)
    ids = {}
    async with db.start() as repos:
        for name, status, old in [
            ("queued", JobStatus.QUEUED, True),
            ("running", JobStatus.RUNNING, True),
            ("new", JobStatus.RUNNING, False),
            ("done", JobStatus.SUCCESS, True),
        ]:
            run_id = await repos.jobs.create_run(
                JobRunCreate(job_name=name, status=status)
            )
            ids[name] = run_id
            if old:
                await repos.session.execute(
                    update(JobRun).where(JobRun.id == run_id).values(created_at=stale)
                )
            await repos.jobs.upsert_batches(
                [
                    JobBatchCreate(
                        run_id=run_id,
                        batch_no=1,
                        offset=0,
                        batch_size=1,
                        status=JobBatchStatus.RUNNING,
                    ),
                    JobBatchCreate(
                        run_id=run_id,
                        batch_no=2,
                        offset=1,
                        batch_size=1,
                        status=JobBatchStatus.SUCCESS,
                    ),
                ]
            )
    async with db.start() as repos:
        assert await repos.jobs.fail_zombie_jobs(heartbeat_timeout_minutes=5, queued_timeout_minutes=5) == 2
    async with db.start() as repos:
        runs = await repos.jobs.fetch_runs(JobRunPageParams())
        batches = await repos.jobs.fetch_batches(
            JobBatchPageParams(), JobBatchFilter(run_id=ids["queued"])
        )
        assert {run.job_name: run.status for run in runs} == {
            "queued": JobStatus.FAILED,
            "running": JobStatus.FAILED,
            "new": JobStatus.RUNNING,
            "done": JobStatus.SUCCESS,
        }
        assert {batch.batch_no: batch.status for batch in batches} == {
            1: JobBatchStatus.FAILED,
            2: JobBatchStatus.SUCCESS,
        }
        assert (
            await repos.jobs.update_runs(
                JobRunUpdate(status=JobStatus.SUCCESS),
                JobRunFilter(id=ids["queued"], statuses=(JobStatus.RUNNING,)),
            )
            == 0
        )


async def test_heartbeat_committing_while_sweep_waits_prevents_false_failure(db):
    async with db.start() as repos:
        run_id = await repos.jobs.create_run(
            JobRunCreate(job_name="race", status=JobStatus.RUNNING)
        )
        await repos.session.execute(
            update(JobRun)
            .where(JobRun.id == run_id)
            .values(
                created_at=datetime.now(UTC) - timedelta(minutes=10),
            )
        )
    entered = asyncio.Event()

    async def sweep():
        async with db.start() as repos:
            entered.set()
            return await repos.jobs.fail_zombie_jobs(heartbeat_timeout_minutes=5, queued_timeout_minutes=5)

    async with db.start() as repos:
        await repos.jobs.heartbeat_run(run_id)
        task = asyncio.create_task(sweep())
        await entered.wait()
        await asyncio.sleep(0.05)
        assert not task.done()
    assert await asyncio.wait_for(task, 3) == 0


async def test_queued_runs_wait_for_the_queued_timeout_not_the_heartbeat_timeout(db):
    # A run waiting in a worker queue behind a long job has no heartbeat; it must survive the
    # heartbeat timeout and only fail once the (longer) queued timeout has passed.
    ages = {"waiting": 30, "abandoned": 120, "running_silent": 30}
    async with db.start() as repos:
        for name, minutes in ages.items():
            status = JobStatus.RUNNING if name.startswith("running") else JobStatus.QUEUED
            run_id = await repos.jobs.create_run(JobRunCreate(job_name=name, status=status))
            await repos.session.execute(
                update(JobRun).where(JobRun.id == run_id)
                .values(created_at=datetime.now(UTC) - timedelta(minutes=minutes))
            )
    async with db.start() as repos:
        assert await repos.jobs.fail_zombie_jobs(heartbeat_timeout_minutes=5, queued_timeout_minutes=60) == 2
    async with db.start() as repos:
        runs = await repos.jobs.fetch_runs(JobRunPageParams())
    assert {run.job_name: run.status for run in runs} == {
        "waiting": JobStatus.QUEUED,
        "abandoned": JobStatus.FAILED,
        "running_silent": JobStatus.FAILED,
    }
