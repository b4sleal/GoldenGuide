"""JobExecution: heartbeat while running, skip runs that are not QUEUED, never leave a run unfinished."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.application.services.jobs.execution import JobExecution
from backend.domain.entities.job_requests import RegistrationImportParams
from backend.domain.entities.jobs import (
    JobBatchStatus,
    JobFailureReason,
    JobRunMetadataKey,
    JobStatus,
)

REQUEST = RegistrationImportParams(term_code="202609")


class DB:
    def __init__(self, status=JobStatus.QUEUED, metadata_json=None):
        self.status = status
        self.metadata_json = metadata_json
        self.heartbeat = asyncio.Event()
        self.jobs = SimpleNamespace(
            update_runs=AsyncMock(side_effect=self.update),
            update_batches=AsyncMock(return_value=1),
            heartbeat_run=AsyncMock(side_effect=lambda run_id: self.heartbeat.set()),
            fetch_runs=AsyncMock(side_effect=lambda **kwargs: [
                SimpleNamespace(status=self.status, metadata_json=self.metadata_json, job_name="j"),
            ]),
        )

    async def update(self, update_model, filters):
        if self.status not in filters.statuses:
            return 0
        self.status = update_model.status
        return 1

    @asynccontextmanager
    async def start(self):
        yield self


class Registry:
    def __init__(self, work):
        self.work = work
        self.calls = []

    async def run(self, run_id, request):
        self.calls.append((run_id, request))
        await self.work()


async def test_heartbeats_while_the_job_runs_and_keeps_its_recorded_outcome():
    db = DB()
    release = asyncio.Event()

    async def work():
        db.status = JobStatus.RUNNING
        await asyncio.wait_for(db.heartbeat.wait(), 1)  # Beats while the job is still working.
        await release.wait()
        db.status = JobStatus.SUCCESS

    registry = Registry(work)
    task = asyncio.create_task(JobExecution(db, registry, heartbeat_seconds=0.01).run(1, REQUEST))
    await asyncio.wait_for(db.heartbeat.wait(), 1)
    release.set()
    await task

    assert registry.calls == [(1, REQUEST)]
    assert db.status == JobStatus.SUCCESS
    db.jobs.update_batches.assert_not_awaited()


@pytest.mark.parametrize(
    ("raises", "reason"),
    [(False, JobFailureReason.MISSING_OUTCOME), (True, JobFailureReason.EXECUTION_ERROR)],
)
async def test_exception_or_missing_outcome_fails_the_run_and_its_batches(raises, reason):
    db = DB()

    async def work():
        if raises:
            raise ValueError("failure")

    await JobExecution(db, Registry(work), heartbeat_seconds=0.01).run(1, REQUEST)

    assert db.status == JobStatus.FAILED
    batches = db.jobs.update_batches.call_args.kwargs
    assert batches["update_model"].error_type == reason
    assert set(batches["filters"].statuses) == {JobBatchStatus.QUEUED, JobBatchStatus.RUNNING}


async def test_cancellation_fails_the_run_and_propagates():
    db = DB()
    started = asyncio.Event()

    async def work():
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(JobExecution(db, Registry(work), heartbeat_seconds=0.01).run(1, REQUEST))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert db.status == JobStatus.FAILED
    assert db.jobs.update_batches.call_args.kwargs["update_model"].error_type == JobFailureReason.INTERRUPTED


@pytest.mark.parametrize("status", [JobStatus.RUNNING, JobStatus.SUCCESS, JobStatus.FAILED])
async def test_a_run_that_is_no_longer_queued_is_not_run_again(status):
    db = DB(status)
    registry = Registry(AsyncMock())

    await JobExecution(db, registry, heartbeat_seconds=0.01).run(1, REQUEST)

    assert registry.calls == []
    assert db.status == status
    db.jobs.update_runs.assert_not_awaited()


async def test_a_worker_runs_the_request_stored_on_the_run():
    db = DB(metadata_json={JobRunMetadataKey.REQUEST: REQUEST.model_dump(mode="json")})

    async def work():
        db.status = JobStatus.SUCCESS

    registry = Registry(work)
    await JobExecution(db, registry, heartbeat_seconds=0.01).run_stored(1)

    assert registry.calls == [(1, REQUEST)]
    assert db.status == JobStatus.SUCCESS


@pytest.mark.parametrize(
    "metadata_json",
    [None, {}, {JobRunMetadataKey.REQUEST: {"key": "not_a_job"}}],
    ids=["no-metadata", "no-request", "unknown-job"],
)
async def test_an_unreadable_stored_request_fails_the_run_without_running_anything(metadata_json):
    db = DB(metadata_json=metadata_json)
    registry = Registry(AsyncMock())

    await JobExecution(db, registry, heartbeat_seconds=0.01).run_stored(1)

    assert registry.calls == []
    assert db.status == JobStatus.FAILED
    assert db.jobs.update_batches.call_args.kwargs["update_model"].error_type == JobFailureReason.INVALID_REQUEST


async def test_a_stored_run_that_is_no_longer_queued_is_not_run_again():
    db = DB(JobStatus.FAILED, metadata_json={JobRunMetadataKey.REQUEST: REQUEST.model_dump(mode="json")})
    registry = Registry(AsyncMock())

    await JobExecution(db, registry, heartbeat_seconds=0.01).run_stored(1)

    assert registry.calls == []
    db.jobs.update_runs.assert_not_awaited()
