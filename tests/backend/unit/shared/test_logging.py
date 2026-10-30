"""Secret redaction and @traced async-generator behavior.

Logging pipeline, trace correlation, settings and exporter tests live in
tests/backend/unit/domain/settings/test_{logging,telemetry}_runtime.py.
"""
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from goldenguide_common.logging import trace_wrapper
from goldenguide_common.logging.configure import redact_sensitive_fields
from goldenguide_common.logging.telemetry import _parse_headers
from goldenguide_common.logging.trace_wrapper import traced


@pytest.fixture
def spans(monkeypatch) -> InMemorySpanExporter:
    """Route @traced spans to an in-memory exporter, without touching the global provider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace_wrapper, "tracer", provider.get_tracer("test"))
    return exporter


def test_redacts_secret_looking_fields_only():
    event = {"event": "x", "api_key": "k", "Authorization": "Bearer t", "session_cookie": "c", "model": "gemini"}
    assert redact_sensitive_fields(None, "info", event) == {
        "event": "x",
        "api_key": "[REDACTED]",
        "Authorization": "[REDACTED]",
        "session_cookie": "[REDACTED]",
        "model": "gemini",
    }


def test_parse_otlp_headers():
    assert _parse_headers(None) is None
    assert _parse_headers("api-key=abc, tenant = wlu") == {"api-key": "abc", "tenant": "wlu"}


async def test_async_generator_children_nest_under_one_span(spans):
    @traced("unit.stream")
    async def stream():
        for i in range(3):
            # Spans created inside the generator (HTTP, SQL, ...) must nest under unit.stream.
            with trace_wrapper.tracer.start_as_current_span("unit.child"):
                pass
            yield i

    assert [item async for item in stream()] == [0, 1, 2]
    finished = spans.get_finished_spans()
    parent = next(s for s in finished if s.name == "unit.stream")
    children = [s for s in finished if s.name == "unit.child"]
    assert len(children) == 3
    assert all(child.parent.span_id == parent.context.span_id for child in children)


async def test_async_generator_failure_marks_span_error(spans):
    @traced("unit.stream_fail")
    async def stream():
        yield 1
        raise RuntimeError("llm reset")

    with pytest.raises(RuntimeError):
        async for _ in stream():
            pass
    (span,) = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.events[0].name == "exception"


async def test_async_generator_closed_early_still_ends_span(spans):
    closed = []

    @traced("unit.stream_early")
    async def stream():
        try:
            yield 1
            yield 2
        finally:
            closed.append(True)

    generator = stream()
    assert await anext(generator) == 1
    await generator.aclose()  # e.g. the student closed the tab mid-answer
    assert closed == [True]
    assert [s.name for s in spans.get_finished_spans()] == ["unit.stream_early"]
