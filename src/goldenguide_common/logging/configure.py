"""Structured logging for one process: application logs and third-party logs share one format.

How logs reach Grafana:
    process stdout (one JSON object per line)
        -> Docker log file
        -> Grafana Alloy (deploy/alloy/config.alloy) parses level / trace_id
        -> Loki (storage + search)
        -> Grafana (Explore; each line links to its trace in Jaeger via trace_id)

The process only writes to stdout and never sends logs over the network itself. That is the
standard container approach (twelve-factor "logs as event streams"): if Loki or the
collector is down, the app keeps running and the log lines stay in Docker. The same output
works unchanged with AWS CloudWatch when deployed to ECS.

Why not ship logs over OTLP from Python? The OpenTelemetry Python *logs* SDK is still
experimental (`opentelemetry.sdk._logs`). Traces use OTLP (telemetry.py); logs are joined to
traces through the `trace_id`/`span_id` fields added below.
"""
from __future__ import annotations

import logging
import sys

import structlog
from opentelemetry import trace

from goldenguide_common.logging.settings import LoggingSettings

# Field names whose values must never appear in logs, matched as case-insensitive substrings.
# This is a safety net: code should not pass secrets to the logger in the first place.
_SENSITIVE_KEY_PARTS = ("password", "secret", "token", "api_key", "apikey", "authorization", "cookie")
_REDACTED = "[REDACTED]"

# Libraries that log every request at INFO. Our own access log (api/middleware/request_context.py)
# already records each request once, so these would only duplicate it.
_QUIET_LOGGERS = ("uvicorn.access", "httpx", "httpcore")


def add_trace_context(logger: object, method_name: str, event_dict: dict) -> dict:
    """Add the active trace/span IDs so Grafana can jump from a log line to its trace."""
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        # Same hex formats that Jaeger and the OTel spec use.
        event_dict["trace_id"] = f"{context.trace_id:032x}"
        event_dict["span_id"] = f"{context.span_id:016x}"
    return event_dict


def redact_sensitive_fields(logger: object, method_name: str, event_dict: dict) -> dict:
    """Replace values of secret-looking top-level fields (e.g. api_key=..., cookie=...)."""
    for key in event_dict:
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            event_dict[key] = _REDACTED
    return event_dict


def configure_logging(settings: LoggingSettings) -> None:
    """Configure logging for this process. Call once at startup, before handling requests.

    After this, both `structlog.get_logger()` and stdlib `logging.getLogger()` (used by uvicorn,
    SQLAlchemy, httpx, ...) produce the same structured output.
    """
    level = logging.getLevelNamesMapping()[settings.level]  # `level` is validated by LoggingSettings.

    # Step 1: fields every log line gets, so lines from different services can be told apart in Loki.
    def add_service(logger: object, method_name: str, event_dict: dict) -> dict:
        event_dict.setdefault("service", settings.service_name)
        event_dict.setdefault("environment", settings.environment)
        return event_dict

    # Step 2: processing chain shared by structlog and stdlib loggers.
    shared_processors = [
        structlog.contextvars.merge_contextvars,  # request_id bound by RequestContextMiddleware
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_service,
        add_trace_context,
        redact_sensitive_fields,  # last, so it also covers fields added above and by contextvars
    ]

    # Step 3: output format. JSON for anything collected by Alloy/CloudWatch, readable text for a terminal.
    # Tracebacks: JSON needs format_exc_info to flatten them into one `exception` string field (so the
    # line stays one JSON object); the console renderer formats tracebacks itself and warns if
    # format_exc_info already did.
    if settings.format == "json":
        final_processors = [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(default=str),
        ]
    else:
        final_processors = [
            structlog.dev.ConsoleRenderer(
                colors=sys.stdout.isatty(),
                # Rich tracebacks print every local variable of every frame by default. One failed
                # import dumped thousands of scraped records into a single log entry, so locals are
                # off: they bloat log storage and can leak student data or secrets.
                exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=False),
            )
        ]

    # Step 4: structlog loggers hand their events to the stdlib logging system,
    # so there is exactly one handler and one output stream for everything.
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Step 5: the single stdout handler. `foreign_pre_chain` applies the shared processors to
    # stdlib records (uvicorn, SQLAlchemy, ...) so they get the same fields as our own logs.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *final_processors,
        ],
    )
    # Always write UTF-8. Windows terminals default to cp1252, which cannot encode the box-drawing
    # characters the console renderer uses for tracebacks, and the whole log line would be lost
    # to a UnicodeEncodeError. Linux containers already use UTF-8, so this changes nothing there.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    # Step 6: replace any handlers installed earlier (by uvicorn or a previous call) with ours.
    root = logging.getLogger()
    for old in root.handlers[:]:
        root.removeHandler(old)
        old.close()
    root.addHandler(handler)
    root.setLevel(level)

    # Step 7: uvicorn installs its own handlers; remove them and let its records propagate
    # to the root handler above, otherwise its lines would be printed twice in two formats.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    # Step 8: silence per-request INFO chatter from libraries (warnings and errors still appear).
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
