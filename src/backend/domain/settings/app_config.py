"""The complete configuration snapshot produced by shared/config/loader.py.

ConfigLoader merges YAML and resolves secrets before constructing this model. Each section
validates its own fields, so a bad configuration fails at startup rather than during a request.
"""
from pydantic import BaseModel, ConfigDict

from backend.domain.settings.ai_behavior import AIBehaviorSettings
from backend.domain.settings.catalog import CatalogSettings
from goldenguide_common.contracts.embedding_models import LocalEmbeddingServiceSettings
from backend.domain.settings.system_settings import SystemSettings


class FrozenConfig(BaseModel):
    model_config = ConfigDict(frozen=True)


class AppConfig(FrozenConfig):
    """Root configuration passed to the composition root to wire concrete adapters."""

    system: SystemSettings
    catalog: CatalogSettings
    ai_behavior: AIBehaviorSettings
    local_embedding_service: LocalEmbeddingServiceSettings

