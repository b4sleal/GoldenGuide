"""Submission stores the request, commits before dispatch, and rejects active runs under the repository lock."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.application.services.jobs.job_submit import JobSubmissionService
from backend.domain.entities.job_requests import WebsiteCrawlParams, parse_job_request
from backend.domain.entities.jobs import JobMode, JobRunMetadataKey, JobStatus
from backend.domain.errors import ConflictError
from backend.domain.settings.scraping import Website

REQUEST = WebsiteCrawlParams(
    site=Website.WLU, mode=JobMode.UPDATE, page_limit=None, concurrency=4, timeout_seconds=30,
)


class AppDB:
    def __init__(self):
        self.events = []
        self.jobs = SimpleNamespace(
            lock_submission=AsyncMock(side_effect=lambda name: self.events.append("locked")),
            fetch_runs=AsyncMock(return_value=[]),
            create_run=AsyncMock(return_value=7),
            update_runs=AsyncMock(return_value=1),
        )

    @asynccontextmanager
    async def start(self):
        yield self
        self.events.append("committed")


async def submit(db, launcher):
    return await JobSubmissionService(db, launcher).submit(job_name="crawl:wlu", mode=JobMode.UPDATE, request=REQUEST)


async def test_request_is_stored_on_the_run_and_committed_before_launch():
    db = AppDB()

    async def launch(run_id, request):
        assert db.events == ["locked", "committed"]
        assert (run_id, request) == (7, REQUEST)

    queued = await submit(db, SimpleNamespace(launch=launch))

    assert queued.run_id == 7 and queued.status == JobStatus.QUEUED
    payload = db.jobs.create_run.call_args.kwargs["payload"]
    assert (payload.job_name, payload.mode, payload.status) == ("crawl:wlu", JobMode.UPDATE, JobStatus.QUEUED)
    # The stored request is plain JSON that reads back as the same request.
    assert parse_job_request(payload.metadata_json[JobRunMetadataKey.REQUEST]) == REQUEST


async def test_existing_run_is_conflict_and_not_dispatched():
    db = AppDB()
    db.jobs.fetch_runs.return_value = [SimpleNamespace(id=4)]
    launcher = SimpleNamespace(launch=AsyncMock())

    with pytest.raises(ConflictError):
        await submit(db, launcher)

    db.jobs.create_run.assert_not_awaited()
    launcher.launch.assert_not_awaited()


@pytest.mark.parametrize("error", [RuntimeError("launch failed"), asyncio.CancelledError()])
async def test_launch_failure_or_request_cancellation_terminalizes_committed_run(error):
    db = AppDB()

    with pytest.raises(type(error)):
        await submit(db, SimpleNamespace(launch=AsyncMock(side_effect=error)))

    update = db.jobs.update_runs.call_args.kwargs
    assert update["update_model"].status == JobStatus.FAILED
    assert update["filters"].statuses == (JobStatus.QUEUED, JobStatus.RUNNING)
