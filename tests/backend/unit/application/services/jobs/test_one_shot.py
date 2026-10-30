"""One-shot outcomes preserve incomplete retrieval and never resurrect terminal runs."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.application.services.jobs.one_shot import OneShotJobRunner
from backend.domain.entities.jobs import (
    JobBatchStatus,
    JobMode,
    JobStatus,
    JobWorkResult,
)
from backend.domain.errors import ConflictError


def app_db(jobs):
    @asynccontextmanager
    async def start():
        yield SimpleNamespace(jobs=jobs)

    return SimpleNamespace(start=start)


@pytest.mark.parametrize("status", [JobStatus.SUCCESS, JobStatus.PARTIAL_SUCCESS])
async def test_one_shot_records_explicit_outcome_and_summary(status):
    jobs = SimpleNamespace(
        update_runs=AsyncMock(return_value=1),
        upsert_batches=AsyncMock(),
        update_batches=AsyncMock(),
    )
    await OneShotJobRunner(app_db(jobs), "crawl").execute(
        run_id=1,
        mode=JobMode.UPDATE,
        work=AsyncMock(
            return_value=JobWorkResult(
                summary={"pages_retryable_error": 1}, status=status
            )
        ),
    )
    assert jobs.update_runs.call_args.kwargs["update_model"].status == status
    assert jobs.update_runs.call_args.kwargs["filters"].statuses == (
        JobStatus.QUEUED,
        JobStatus.RUNNING,
    )
    batch_status = jobs.update_batches.call_args.kwargs["update_model"].status
    assert batch_status == (
        JobBatchStatus.SUCCESS if status == JobStatus.SUCCESS else JobBatchStatus.FAILED
    )


async def test_terminal_run_cannot_be_restarted():
    jobs = SimpleNamespace(
        update_runs=AsyncMock(return_value=0), upsert_batches=AsyncMock()
    )
    work = AsyncMock()
    with pytest.raises(ConflictError):
        await OneShotJobRunner(app_db(jobs), "crawl").execute(
            run_id=1, mode=JobMode.UPDATE, work=work
        )
    work.assert_not_awaited()
    jobs.upsert_batches.assert_not_awaited()
