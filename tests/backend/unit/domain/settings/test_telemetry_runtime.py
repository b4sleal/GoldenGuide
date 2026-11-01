"""Verify exporter configuration without needing a running Collector."""
from unittest.mock import Mock

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from goldenguide_common.logging import telemetry
from goldenguide_common.logging.settings import TelemetrySettings


def test_exporter_receives_configuration_and_resource(monkeypatch):
    exporter = Mock()
    export_ctor = Mock(return_value=exporter)
    install = Mock()
    monkeypatch.setattr(telemetry, "OTLPSpanExporter", export_ctor)
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", install)
    monkeypatch.setattr(telemetry, "_provider", None)
    # Don't patch httpx globally for the rest of the test session.
    monkeypatch.setattr(telemetry, "HTTPXClientInstrumentor", Mock())

    settings = TelemetrySettings(
        environment="production", service_name="goldenguide-worker",
        version="v2", otlp_endpoint="http://otel-collector:4317",
        otlp_insecure=True, otlp_headers="x-api-key=redacted",
        sample_ratio=0.3,
    )
    telemetry.configure_telemetry(settings)
    export_ctor.assert_called_once_with(
        endpoint="http://otel-collector:4317",
        headers={"x-api-key": "redacted"}, insecure=True,
    )
    provider = install.call_args.args[0]
    assert isinstance(provider, TracerProvider)
    assert provider.resource.attributes["service.name"] == "goldenguide-worker"
    assert provider.resource.attributes["service.version"] == "v2"
    assert any(isinstance(processor, BatchSpanProcessor) for processor in provider._active_span_processor._span_processors)
    telemetry.shutdown_telemetry()
    exporter.shutdown.assert_called_once()
    # A second shutdown must not change process state.
    telemetry.shutdown_telemetry()
    exporter.shutdown.assert_called_once()


def test_invalid_export_headers_do_not_install_provider(monkeypatch):
    install = Mock()
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", install)
    with pytest.raises(ValueError, match="Invalid OTEL_EXPORTER_OTLP_HEADERS"):
        telemetry.configure_telemetry(TelemetrySettings(
            otlp_endpoint="http://otel-collector:4317", otlp_headers="invalid"
        ))
    install.assert_not_called()
