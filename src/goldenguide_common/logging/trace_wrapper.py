"""@traced: wrap one important business step in its own trace span.

Automatic instrumentation already covers HTTP and SQL (see telemetry.py). Use this decorator
for steps that matter when explaining latency or failures, such as "llm.generate" or
"retrieval.resolve". Each span records its duration, and if the function raises, the exception
and an ERROR status. The exception is always re-raised: tracing never hides an error.

Keep span names stable and low-cardinality ("llm.generate", not "llm.generate for CP317"),
because they are used to group and compare requests in Jaeger/Grafana.
"""
from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)


def traced(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a sync function, coroutine function, or async generator with a span called `name`."""

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        # Case 1: async generator (e.g. a streaming LLM call).
        # The span must stay open across `yield`s, but the caller's context can change between
        # iterations (the consumer may resume the generator from another task), so a plain
        # `with start_as_current_span` around the loop would attach/detach context in different
        # tasks and fail. Instead: start the span once, activate it around each step, end it once.
        if inspect.isasyncgenfunction(func):
            @functools.wraps(func)
            async def async_generator(*args: Any, **kwargs: Any):
                span = tracer.start_span(name)
                generator = func(*args, **kwargs)
                try:
                    while True:
                        # Activate the span only while the generator body runs, so child
                        # spans (HTTP, SQL) created inside it nest under this span.
                        with trace.use_span(span, end_on_exit=False):
                            try:
                                item = await anext(generator)
                            except StopAsyncIteration:
                                return
                        yield item
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    raise
                finally:
                    # Close the inner generator too (e.g. the consumer disconnected), then end the span.
                    await generator.aclose()
                    span.end()

            return async_generator

        # Case 2: coroutine. start_as_current_span records exceptions and sets ERROR status by default.
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                with tracer.start_as_current_span(name):
                    return await func(*args, **kwargs)

            return async_wrapper

        # Case 3: regular function.
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            with tracer.start_as_current_span(name):
                return func(*args, **kwargs)

        return sync_wrapper

    return decorate
