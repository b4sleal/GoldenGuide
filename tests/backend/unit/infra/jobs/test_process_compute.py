"""ProcessPoolComputeExecutor runs work in child processes and keeps result/exception semantics.

Children start with `spawn`, so these functions must be importable (module-level), like real parsers.
"""
import os

import pytest

from backend.infra.jobs.process_compute import ProcessPoolComputeExecutor


def no_setup() -> None:
    """Child initializer stand-in (the worker configures logging here)."""


def add_and_report_pid(a: int, *, b: int) -> tuple[int, int]:
    return a + b, os.getpid()


def fail() -> None:
    raise ValueError("unmapped subject codes")


@pytest.fixture(scope="module")
def pool():
    executor = ProcessPoolComputeExecutor(max_workers=1, initializer=no_setup)
    yield executor
    executor.shutdown()


async def test_returns_the_result_computed_in_another_process(pool):
    result, child_pid = await pool.run(add_and_report_pid, 2, b=3)

    assert result == 5
    assert child_pid != os.getpid()


async def test_exceptions_propagate_unchanged(pool):
    with pytest.raises(ValueError, match="unmapped subject codes"):
        await pool.run(fail)
