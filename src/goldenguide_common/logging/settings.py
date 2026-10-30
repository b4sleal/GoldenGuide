"""Validated, immutable observability configuration; no environment or SDK dependencies."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoggingSettings(BaseModel):
    """Structured-log identity, severity and output format for one process."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service_name: str = Field(default="goldenguide-api", min_length=1)
    environment: str = "development"
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "console"


class TelemetrySettings(BaseModel):
    """OTLP trace-export policy shared by API, workers and embedding processes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service_name: str = Field(default="goldenguide-api", min_length=1)
    environment: str = "development"
    version: str = "unknown"
    otlp_endpoint: str | None = None
    otlp_headers: str | None = None
    otlp_insecure: bool = False
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_production_exporter(self) -> "TelemetrySettings":
        # A production instance must not silently discard all distributed traces.
        if self.environment == "production" and not self.otlp_endpoint:
            raise ValueError("Production telemetry requires an OTLP endpoint")
        return self


class ObservabilitySettings(BaseModel):
    """Single configuration snapshot used to initialize logging and tracing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    logging: LoggingSettings
    telemetry: TelemetrySettings
