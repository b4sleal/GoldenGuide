"""OpenTelemetry tracing for one process: SDK setup, export, and library instrumentation.

How traces reach Jaeger:
    process -> OTLP/gRPC -> OpenTelemetry Collector (deploy/otel/collector.yaml) -> Jaeger

Cross-service tracing: outgoing HTTPX requests carry a W3C `traceparent` header, and every
GoldenGuide service instruments its FastAPI app. So a chat request, the backend's call to the
embedding service, and that service's own work all appear as ONE trace, under each service's
own `service.name` (OTEL_SERVICE_NAME).

What gets spans automatically once configured:
    - incoming HTTP requests     FastAPIInstrumentor (each service's composition root)
    - outgoing HTTP calls        HTTPX (embedding service, Qdrant, Gemini and other SDKs on httpx)
    - SQL statements             SQLAlchemy (backend only: core/startup/runtime.py)
Business steps (routing, retrieval, generation) use the @traced decorator (trace_wrapper.py).
"""
from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from goldenguide_common.logging.settings import TelemetrySettings

logger = structlog.get_logger(__name__)

# The process-wide provider. OpenTelemetry allows setting the global provider only once per
# process, so it is created once and kept even after shutdown.
_provider: TracerProvider | None = None


def configure_telemetry(settings: TelemetrySettings) -> None:
    """Install the tracer provider and instrument shared libraries. Safe to call more than once."""
    global _provider
    if _provider is not None:
        return

    # Step 1: identity attached to every span from this process. Grafana/Jaeger group by these.
    resource = Resource.create({
        SERVICE_NAME: settings.service_name,
        SERVICE_VERSION: settings.version,
        "deployment.environment.name": settings.environment,
    })

    # Step 2: sampling. ParentBased follows the caller's decision, so a trace is never half-recorded
    # across services. The ratio applies only to traces that start in this process.
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.sample_ratio)),
    )

    # Step 3: export. Without an endpoint (e.g. running outside Docker), spans are still created,
    # so log lines keep their trace_id, but they are not exported. Production cannot get here:
    # TelemetrySettings refuses a production config without an endpoint.
    if settings.otlp_endpoint:
        exporter = OTLPSpanExporter(
            endpoint=settings.otlp_endpoint,
            headers=_parse_headers(settings.otlp_headers),
            insecure=settings.otlp_insecure,
        )
        # Batching sends spans in the background, so request latency never waits on the collector.
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        logger.warning("telemetry.export_disabled", reason="no OTEL_EXPORTER_OTLP_ENDPOINT configured")

    # Step 4: make it the global provider that all tracers and instrumentors use.
    trace.set_tracer_provider(provider)
    _provider = provider

    # Step 5: instrument HTTPX at class level, so clients created before or after this point are
    # covered. This is what carries the trace into the embedding service.
    HTTPXClientInstrumentor().instrument()
    # Libraries only some services use (e.g. SQLAlchemy in the backend) are instrumented in
    # that service's startup code, so shared code never imports packages a service lacks.

    logger.info(
        "telemetry.configured",
        service_name=settings.service_name,
        exporting=bool(settings.otlp_endpoint),
        sample_ratio=settings.sample_ratio,
    )


def _parse_headers(value: str | None) -> dict[str, str] | None:
    """Parse OTEL_EXPORTER_OTLP_HEADERS ("key=value,key2=value2"). Values may be credentials: never log them."""
    if not value:
        return None
    headers: dict[str, str] = {}
    for entry in value.split(","):
        key, separator, content = entry.partition("=")
        if not separator or not key.strip():
            raise ValueError("Invalid OTEL_EXPORTER_OTLP_HEADERS; expected key=value pairs separated by commas")
        headers[key.strip()] = content.strip()
    return headers


def shutdown_telemetry() -> None:
    """Flush buffered spans at process exit. The provider is never re-created afterwards."""
    if _provider is not None:
        _provider.shutdown()
