"""InProcessJobLauncher detaches runs from the request and fails interrupted runs on shutdown."""

import asyncio

import pytest

from backend.domain.entities.job_requests import RegistrationImportParams
from backend.domain.entities.jobs import JobFailureReason
from backend.domain.errors import DependencyUnavailableError
from backend.infra.jobs.in_process_launcher import InProcessJobLauncher

REQUEST = RegistrationImportParams(term_code="202609")


class FakeExecution:
    """JobRunExecutor whose runs block until released; records interruption handling."""

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.ran: list[tuple[int, object]] = []
        self.failed: list[tuple[int, JobFailureReason]] = []

    async def run(self, run_id, request):
        self.ran.append((run_id, request))
        self.started.set()
        await self.release.wait()

    async def fail_if_unfinished(self, run_id, reason):
        self.failed.append((run_id, reason))


async def test_launch_returns_before_the_run_finishes():
    execution = FakeExecution()
    launcher = InProcessJobLauncher(execution)

    await launcher.launch(1, REQUEST)
    await asyncio.wait_for(execution.started.wait(), 1)

    assert execution.ran == [(1, REQUEST)]
    tasks = list(launcher._tasks)
    assert tasks and not tasks[0].done()  # Still running: submission did not wait for it.
    execution.release.set()
    await asyncio.gather(*tasks)
    assert launcher._tasks == {}


@pytest.mark.parametrize("let_start", [False, True])
async def test_shutdown_cancels_runs_and_fails_them_even_before_their_first_instruction(let_start):
    execution = FakeExecution()
    launcher = InProcessJobLauncher(execution)

    await launcher.launch(1, REQUEST)
    if let_start:
        await asyncio.wait_for(execution.started.wait(), 1)
    await launcher.shutdown()

    assert execution.failed == [(1, JobFailureReason.INTERRUPTED)]
    with pytest.raises(DependencyUnavailableError):
        await launcher.launch(2, REQUEST)
