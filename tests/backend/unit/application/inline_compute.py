"""A ComputeExecutor for unit tests: runs work inline and records what was offloaded."""
from collections.abc import Callable


class InlineCompute:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run[**P, R](self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        self.calls.append(fn.__name__)
        return fn(*args, **kwargs)
