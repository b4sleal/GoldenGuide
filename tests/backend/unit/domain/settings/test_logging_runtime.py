"""Behavior tests: capture actual rendered JSON, trace context and exception output."""
import io
import json
import logging
import time

import pytest
import structlog
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from goldenguide_common.logging.settings import LoggingSettings
from goldenguide_common.logging import trace_wrapper
from goldenguide_common.logging.configure import configure_logging


@pytest.fixture
def json_logs():
    """Test the real JSON logging pipeline without pytest stdout capture races.

    Each test owns a StringIO sink attached to the formatter installed by
    configure_logging(). This works with pytest's capture mode and on CI.
    """
    root = logging.getLogger()
    previous_handlers = list(root.handlers)
    previous_level = root.level
    # Detach pytest handlers first: configure_logging closes handlers it replaces.
    # Preserve them so pytest capture continues working after this fixture.
    for old in previous_handlers:
        root.removeHandler(old)
    configure_logging(LoggingSettings(
        service_name="test-api", environment="testing", format="json",
    ))
    handler = root.handlers[0]
    sink = io.StringIO()
    handler.setStream(sink)

    def read_events():
        handler.flush()
        return [json.loads(line) for line in sink.getvalue().splitlines() if line.strip()]

    try:
        yield read_events
    finally:
        structlog.contextvars.clear_contextvars()
        root.removeHandler(handler)
        handler.close()
        for old in previous_handlers:
            if old not in root.handlers:
                root.addHandler(old)
        root.setLevel(previous_level)
        # Reset cached loggers created during this test, without resetting the
        # global structlog configuration used by subsequent tests.
        sink.close()


def test_logs_have_metadata_and_context(json_logs):
    structlog.contextvars.bind_contextvars(request_id="request-123")
    structlog.get_logger("sample").info("test.operation", duration_ms=14.2)
    event, = json_logs()
    assert event["event"] == "test.operation"
    assert event["request_id"] == "request-123"
    assert event["service"] == "test-api"
    assert event["duration_ms"] == 14.2
    assert event["level"] == "info"
    assert "timestamp" in event


def test_exception_has_one_complete_traceback(json_logs):
    def fail():
        raise ValueError("test failure")
    try:
        fail()
    except ValueError:
        structlog.get_logger("sample").exception("operation.failed")
    events = json_logs()
    assert len(events) == 1  # No duplicated application/full exceptions.
    assert events[0]["event"] == "operation.failed"
    assert "ValueError: test failure" in events[0]["exception"]
    assert "fail" in events[0]["exception"]


def test_standard_library_logs_use_same_json_pipeline(json_logs):
    logging.getLogger("foreign.adapter").warning("foreign warning")
    event, = json_logs()
    assert event["event"] == "foreign warning"
    assert event["level"] == "warning"
    assert event["service"] == "test-api"


def test_trace_ids_are_correlated_with_json_logs(json_logs):
    provider = TracerProvider()
    tracer = provider.get_tracer("tests")
    with tracer.start_as_current_span("db.query") as span:
        structlog.get_logger("sample").info("db.finished")
        expected = span.get_span_context()
    event, = json_logs()
    assert event["trace_id"] == f"{expected.trace_id:032x}"
    assert event["span_id"] == f"{expected.span_id:016x}"
    provider.shutdown()


@pytest.fixture
def recorded_spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace_wrapper, "tracer", provider.get_tracer("tests"))
    yield exporter
    provider.shutdown()


@pytest.mark.asyncio
async def test_async_failure_records_exception_and_duration(recorded_spans):
    @trace_wrapper.traced("chat.router")
    async def fail():
        import asyncio
        await asyncio.sleep(0.012)
        raise RuntimeError("router unavailable")

    with pytest.raises(RuntimeError, match="router unavailable"):
        await fail()
    span, = recorded_spans.get_finished_spans()
    assert span.name == "chat.router"
    assert span.end_time - span.start_time >= 8_000_000  # ns; real awaited time.
    assert span.status.status_code.name == "ERROR"
    assert any(e.name == "exception" and "router unavailable" in str(e.attributes) for e in span.events)


@pytest.mark.asyncio
async def test_async_stream_span_lasts_until_consumed(recorded_spans):
    @trace_wrapper.traced("chat.stream")
    async def stream():
        yield "first"
        import asyncio
        await asyncio.sleep(0.012)
        yield "second"

    generated = stream()
    assert recorded_spans.get_finished_spans() == ()
    assert [item async for item in generated] == ["first", "second"]
    span, = recorded_spans.get_finished_spans()
    assert span.end_time - span.start_time >= 8_000_000


def test_sync_operation_records_duration(recorded_spans):
    @trace_wrapper.traced("course.compile")
    def compile_course():
        time.sleep(0.01)
        return "ok"

    assert compile_course() == "ok"
    span, = recorded_spans.get_finished_spans()
    assert span.name == "course.compile"
    assert span.end_time - span.start_time >= 7_000_000
