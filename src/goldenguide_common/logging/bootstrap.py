"""Single entry point that sets up logging and tracing for any GoldenGuide process.

Every service (API backend, embedding service, future workers) calls configure_observability()
once at startup, before serving traffic. That is what makes their logs and traces look the same
and join up across service boundaries.

Configuration comes from standard OpenTelemetry environment variable names, so the same
settings work with the Collector, AWS ADOT, or any OTLP backend:

    OTEL_SERVICE_NAME                    service name shown in Jaeger/Grafana (one per service)
    OTEL_EXPORTER_OTLP_ENDPOINT          collector address, e.g. http://otel-collector:4317
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT   optional traces-only override of the above
    OTEL_EXPORTER_OTLP_HEADERS           optional "key=value,..." auth headers for hosted backends
    OTEL_EXPORTER_OTLP_INSECURE          "true" for plaintext gRPC inside a private network
    OTEL_TRACES_SAMPLER_ARG              fraction of new traces to keep, 0.0-1.0
    APP_ENV / APP_VERSION                deployment.environment.name / service.version
    LOG_LEVEL                            DEBUG | INFO | WARNING | ERROR | CRITICAL
    LOG_FORMAT                           json (containers/production) | console (local terminal)
"""
from __future__ import annotations

from goldenguide_common.logging.settings import LoggingSettings, ObservabilitySettings, TelemetrySettings
from goldenguide_common.config.secret_reader import SecretReader
from goldenguide_common.logging.configure import configure_logging
from goldenguide_common.logging.telemetry import configure_telemetry


def configure_observability(
        reader: SecretReader,
        *,
        default_service_name: str = "goldenguide-api",
) -> ObservabilitySettings:
    """Read settings once, validate them, then configure logging followed by tracing.

    `default_service_name` is used only when OTEL_SERVICE_NAME is unset, so each service passes
    its own name and a missing variable can never make two services report under one name.
    The reader is used only here and is not kept by any logging component.
    """
    # Step 1: read raw values.
    environment = reader.get("APP_ENV", "development")
    service = reader.get("OTEL_SERVICE_NAME", default_service_name)
    endpoint = reader.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or reader.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    # Step 2: build one immutable, validated snapshot. Pydantic rejects bad values here, at boot,
    # e.g. an unknown LOG_LEVEL or a production config without an exporter.
    settings = ObservabilitySettings(
        logging=LoggingSettings(
            service_name=service,
            environment=environment,
            level=reader.get("LOG_LEVEL", "INFO").upper(),
            format=reader.get("LOG_FORMAT", "json" if environment == "production" else "console"),
        ),
        telemetry=TelemetrySettings(
            service_name=service,
            environment=environment,
            version=reader.get("APP_VERSION", "unknown"),
            otlp_endpoint=endpoint,
            otlp_headers=reader.get("OTEL_EXPORTER_OTLP_HEADERS"),
            otlp_insecure=_parse_bool("OTEL_EXPORTER_OTLP_INSECURE", reader.get("OTEL_EXPORTER_OTLP_INSECURE", "false")),
            sample_ratio=reader.get("OTEL_TRACES_SAMPLER_ARG", "1.0"),
        ),
    )

    # Step 3: logging first, so anything telemetry setup logs is already structured.
    configure_logging(settings.logging)
    configure_telemetry(settings.telemetry)
    return settings


def _parse_bool(name: str, value: str) -> bool:
    """Accept only 'true'/'false', so values like 'yes' or '0' fail loudly instead of guessing."""
    normalized = value.strip().casefold()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be 'true' or 'false', got {value!r}")
    return normalized == "true"
