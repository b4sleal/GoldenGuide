"""ThreadComputeExecutor runs work off the event loop thread and keeps result/exception semantics."""
import threading

import pytest

from backend.infra.jobs.thread_compute import ThreadComputeExecutor


async def test_returns_the_result_and_runs_off_the_event_loop_thread():
    loop_thread = threading.get_ident()

    def work(a, *, b):
        return a + b, threading.get_ident()

    result, worker_thread = await ThreadComputeExecutor().run(work, 2, b=3)

    assert result == 5
    assert worker_thread != loop_thread


async def test_exceptions_propagate_unchanged():
    def fail():
        raise ValueError("unmapped subject codes")

    with pytest.raises(ValueError, match="unmapped subject codes"):
        await ThreadComputeExecutor().run(fail)
