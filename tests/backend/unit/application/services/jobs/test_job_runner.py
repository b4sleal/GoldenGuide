"""BatchJobRunner: batch failures are isolated; a failure outside the batches marks the run FAILED."""
import asyncio
from contextlib import asynccontextmanager

import pytest

from backend.application.services.jobs.job_runner import BatchJobRunner
from backend.domain.entities.jobs import JobBatchResult, JobBatchStatus, JobStatus


class FakeJobs:
    def __init__(self, fail_final_update=False):
        self.fail_final_update = fail_final_update
        self.run_statuses = []

    async def update_runs(self, update_model, filters):
        if self.fail_final_update and update_model.finished_at and update_model.status != JobStatus.FAILED:
            raise ConnectionError("database down")
        self.run_statuses.append(update_model.status)

    async def heartbeat_run(self, run_id):
        pass

    async def upsert_batches(self, batches):
        pass

    async def update_batches(self, update_model, filters):
        pass


class FakeAppDB:
    def __init__(self, jobs):
        self.jobs = jobs

    @asynccontextmanager
    async def start(self):
        yield self


class Executor:
    """Two batches of 10 rows; batch 2 fails."""

    async def count_total(self):
        return 20

    async def execute_batch(self, batch):
        if batch.batch_no == 2:
            raise ValueError("bad rows")
        return JobBatchResult(processed_count=batch.batch_size)


async def test_failed_batch_gives_partial_success():
    jobs = FakeJobs()

    result = await BatchJobRunner(FakeAppDB(jobs), "job", Executor()).execute(run_id=1, batch_size=10)

    assert result.status == JobStatus.PARTIAL_SUCCESS
    assert [b.batch_no for b in result.failed_batches] == [2]
    assert jobs.run_statuses == [JobStatus.RUNNING, JobStatus.PARTIAL_SUCCESS]


async def test_final_state_failure_marks_the_run_failed_and_reraises():
    jobs = FakeJobs(fail_final_update=True)

    with pytest.raises(ConnectionError):
        await BatchJobRunner(FakeAppDB(jobs), "job", Executor()).execute(run_id=1, batch_size=10)

    assert jobs.run_statuses == [JobStatus.RUNNING, JobStatus.FAILED]


async def test_fatal_batch_state_failure_stops_siblings_before_run_is_failed():
    started, stopped = asyncio.Event(), asyncio.Event()

    class Jobs(FakeJobs):
        async def update_batches(self, update_model, filters):
            if filters.batch_no == 2 and update_model.status == JobBatchStatus.FAILED:
                raise ConnectionError("cannot persist failure")
            return 1

        async def update_runs(self, update_model, filters):
            if update_model.status == JobStatus.FAILED:
                assert stopped.is_set(), "run failed while a sibling was still executing"
            return await super().update_runs(update_model, filters)

    class BlockingExecutor(Executor):
        async def execute_batch(self, batch):
            if batch.batch_no == 2:
                await started.wait()
                raise ValueError("bad batch")
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

    jobs = Jobs()
    with pytest.raises(ConnectionError):
        await asyncio.wait_for(BatchJobRunner(FakeAppDB(jobs), "job", BlockingExecutor()).execute(
            run_id=1, batch_size=10,
        ), 1)
    assert stopped.is_set()
    assert jobs.run_statuses == [JobStatus.RUNNING, JobStatus.FAILED]
