"""System-level YAML configuration validated when AppConfig is loaded.

Process logging is configured by shared/logging/bootstrap.py from observability settings.
These models describe the system.logging section; they do not install handlers or emit logs.
"""
from pydantic import BaseModel, ConfigDict

from backend.domain.settings.jobs import JobSettings
from backend.domain.settings.oidc import OIDCPolicy
from backend.domain.settings.service_clients import ServiceClientSettings


class FrozenSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

class LoggingSettings(FrozenSettings):
    """The logging level supplied by the system YAML section."""

    level: str


class SystemSettings(FrozenSettings):
    """System configuration grouped separately from providers and AI behavior."""

    logging: LoggingSettings
    oidc: OIDCPolicy
    jobs: JobSettings
    # Machine callers keyed by name (see service_clients.py). Clients without key hashes are disabled.
    service_clients: dict[str, ServiceClientSettings]
