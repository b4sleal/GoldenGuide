"""Contract for running CPU-bound work (parsing, conversion) without blocking the event loop."""
from collections.abc import Callable
from typing import Protocol


class ComputeExecutor(Protocol):
    """Runs a synchronous, CPU-bound function off the event loop and returns its result.

    `fn` must be pure with respect to the caller: it reads its arguments and returns a value, without
    I/O or mutating shared state, so an implementation may run it in a thread or another process.
    Exceptions raised by `fn` propagate to the caller unchanged.
    """
    async def run[**P, R](self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        ...
