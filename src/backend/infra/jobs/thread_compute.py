"""ComputeExecutor that runs work in the default thread pool.

Keeps the event loop free to serve requests and heartbeats while a job parses. Only one thread runs
Python code at a time, so this restores responsiveness, not throughput; a process-pool implementation
of the same port is what would parallelize parsing across cores.
"""
import asyncio
from collections.abc import Callable


class ThreadComputeExecutor:
    async def run[**P, R](self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        # to_thread copies contextvars, so structured-log and trace context carry into the worker thread.
        return await asyncio.to_thread(fn, *args, **kwargs)
