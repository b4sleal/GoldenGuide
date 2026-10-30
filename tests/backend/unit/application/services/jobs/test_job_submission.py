"""Submission commits before dispatch and rejects active runs under the repository lock."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.application.services.jobs.job_submit import JobSubmissionService
from backend.domain.entities.jobs import JobMode, JobStatus
from backend.domain.errors import ConflictError


class AppDB:
    def __init__(self):
        self.events = []
        self.jobs = SimpleNamespace(
            lock_submission=AsyncMock(
                side_effect=lambda name: self.events.append("locked")
            ),
            fetch_runs=AsyncMock(return_value=[]),
            create_run=AsyncMock(return_value=7),
            update_runs=AsyncMock(return_value=1),
        )

    @asynccontextmanager
    async def start(self):
        yield self
        self.events.append("committed")


async def test_committed_before_launch_and_work_not_awaited_by_submission():
    db = AppDB()
    work = AsyncMock()

    async def launch(run_id, callback):
        assert db.events == ["locked", "committed"]
        assert run_id == 7
        await callback()

    queued = await JobSubmissionService(db, SimpleNamespace(launch=launch)).submit(
        job_name="crawl:wlu",
        mode=JobMode.UPDATE,
        metadata={},
        work=work,
    )
    assert queued.run_id == 7 and queued.status == JobStatus.QUEUED
    work.assert_awaited_once_with(7)


async def test_existing_run_is_conflict_and_not_dispatched():
    db = AppDB()
    db.jobs.fetch_runs.return_value = [SimpleNamespace(id=4)]
    launcher = SimpleNamespace(launch=AsyncMock())
    with pytest.raises(ConflictError):
        await JobSubmissionService(db, launcher).submit(
            job_name="j", mode=JobMode.UPDATE, metadata={}, work=AsyncMock()
        )
    db.jobs.create_run.assert_not_awaited()
    launcher.launch.assert_not_awaited()


@pytest.mark.parametrize(
    "error", [RuntimeError("launch failed"), asyncio.CancelledError()]
)
async def test_launch_failure_or_request_cancellation_terminalizes_committed_run(error):
    db = AppDB()
    launcher = SimpleNamespace(launch=AsyncMock(side_effect=error))
    with pytest.raises(type(error)):
        await JobSubmissionService(db, launcher).submit(
            job_name="j", mode=JobMode.UPDATE, metadata={}, work=AsyncMock()
        )
    update = db.jobs.update_runs.call_args.kwargs
    assert update["update_model"].status == JobStatus.FAILED
    assert update["filters"].statuses == (JobStatus.QUEUED, JobStatus.RUNNING)
