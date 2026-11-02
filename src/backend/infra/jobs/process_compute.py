"""ComputeExecutor that runs work in a pool of worker processes (job workers only).

Unlike threads, separate processes parse in parallel on several cores, so imports get faster with
more `system.jobs.worker.compute_processes`. The cost is that each call's function and arguments are
pickled to a child process and the result pickled back, so offloaded functions must be module-level
(or bound to plain, picklable objects) and take plain data: HTML, records, settings, lexicons.

Children start with `spawn`: a fresh interpreter, never a fork of a process that already runs an
event loop, threads and connection pools. `initializer` runs once in each child (e.g. to configure
structured logging, which a fresh interpreter does not have).
"""
from __future__ import annotations

import asyncio
import functools
import multiprocessing
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor

START_METHOD = "spawn"


class ProcessPoolComputeExecutor:
    def __init__(self, max_workers: int, initializer: Callable[[], None]) -> None:
        self._pool = ProcessPoolExecutor(
            max_workers=max_workers,
            mp_context=multiprocessing.get_context(START_METHOD),
            initializer=initializer,
        )

    async def run[**P, R](self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        # A child that dies (e.g. killed for memory) raises BrokenProcessPool here, failing the job's
        # batch with that error rather than hanging.
        return await asyncio.get_running_loop().run_in_executor(self._pool, functools.partial(fn, *args, **kwargs))

    def shutdown(self) -> None:
        """Stop the children; work not yet started is cancelled, running work is awaited."""
        self._pool.shutdown(wait=True, cancel_futures=True)
