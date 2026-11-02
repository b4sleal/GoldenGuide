"""The sweep applies the heartbeat timeout to running runs and the longer queued timeout to queued ones."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.application.services.jobs.zombie_sweep import sweep_once
from backend.domain.settings.jobs import JobExecutionMode, JobSettings, WorkerSettings

WORKER = WorkerSettings(concurrency=1, shutdown_graceful_timeout_seconds=60, db_pool_max_size=4, compute_processes=2)


def settings(**overrides) -> JobSettings:
    values = {
        "execution": JobExecutionMode.WORKER, "heartbeat_seconds": 30, "zombie_timeout_minutes": 5,
        "queued_timeout_minutes": 1440, "zombie_sweep_seconds": 120, "worker": WORKER,
    }
    return JobSettings(**(values | overrides))


async def test_sweep_passes_both_timeouts_to_the_repository():
    jobs = SimpleNamespace(fail_zombie_jobs=AsyncMock(return_value=2))

    @asynccontextmanager
    async def start():
        yield SimpleNamespace(jobs=jobs)

    assert await sweep_once(SimpleNamespace(start=start), settings()) == 2
    jobs.fail_zombie_jobs.assert_awaited_once_with(heartbeat_timeout_minutes=5, queued_timeout_minutes=1440)


def test_queued_runs_cannot_time_out_before_silent_running_ones():
    with pytest.raises(ValidationError, match="queued_timeout_minutes"):
        settings(queued_timeout_minutes=4)
