"""Real asyncio execution covers detached work, heartbeat, shutdown and missing outcomes."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.domain.entities.jobs import JobBatchStatus, JobStatus
from backend.domain.errors import DependencyUnavailableError
from backend.infra.jobs.in_process_launcher import InProcessJobLauncher


class DB:
    def __init__(self):
        self.status = JobStatus.QUEUED
        self.heartbeat = asyncio.Event()
        self.jobs = SimpleNamespace(
            update_runs=AsyncMock(side_effect=self.update),
            update_batches=AsyncMock(return_value=1),
            heartbeat_run=AsyncMock(side_effect=lambda run_id: self.heartbeat.set()),
            fetch_runs=AsyncMock(
                side_effect=lambda **kwargs: [SimpleNamespace(status=self.status)]
            ),
        )

    async def update(self, update_model, filters):
        if self.status not in filters.statuses:
            return 0
        self.status = update_model.status
        return 1

    @asynccontextmanager
    async def start(self):
        yield self


async def test_launch_returns_before_work_finishes_and_keeps_heartbeating():
    db = DB()
    launcher = InProcessJobLauncher(db, heartbeat_seconds=0.01)
    started, release = asyncio.Event(), asyncio.Event()

    async def work():
        started.set()
        await release.wait()
        db.status = JobStatus.SUCCESS

    await launcher.launch(1, work)
    await asyncio.wait_for(started.wait(), 1)
    await asyncio.wait_for(db.heartbeat.wait(), 1)
    assert db.status == JobStatus.QUEUED
    tasks = list(launcher._tasks)
    release.set()
    await asyncio.gather(*tasks)
    await launcher.shutdown()
    assert db.status == JobStatus.SUCCESS
    db.jobs.update_batches.assert_not_awaited()


@pytest.mark.parametrize("let_start", [False, True])
async def test_shutdown_fails_run_and_unfinished_batches_even_before_first_instruction(
    let_start,
):
    db = DB()
    launcher = InProcessJobLauncher(db, 0.01)
    started = asyncio.Event()

    async def work():
        started.set()
        await asyncio.Event().wait()

    await launcher.launch(1, work)
    if let_start:
        await asyncio.wait_for(started.wait(), 1)
    await launcher.shutdown()
    assert db.status == JobStatus.FAILED
    filters = db.jobs.update_batches.call_args.kwargs["filters"]
    assert set(filters.statuses) == {JobBatchStatus.QUEUED, JobBatchStatus.RUNNING}
    with pytest.raises(DependencyUnavailableError):
        await launcher.launch(2, work)


@pytest.mark.parametrize("raises", [False, True])
async def test_exception_or_missing_terminal_outcome_is_failed(raises):
    db = DB()
    launcher = InProcessJobLauncher(db, 0.01)

    async def work():
        if raises:
            raise ValueError("failure")

    await launcher.launch(1, work)
    await asyncio.gather(*list(launcher._tasks))
    assert db.status == JobStatus.FAILED
    await launcher.shutdown()
