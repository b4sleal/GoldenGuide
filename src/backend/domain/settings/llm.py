"""Typed settings for LLM providers (Gemini, OpenAI, Claude)."""
from collections.abc import Mapping

from pydantic import SecretStr

from backend.domain.common import providers_enum as Providers
from goldenguide_common.contracts.embedding_models import FrozenModelSettings


class GeminiLLMSettings(FrozenModelSettings):
    provider: Providers.LLMProvider
    model_name: str
    api_key: SecretStr


class OpenAILLMSettings(FrozenModelSettings):
    provider: Providers.LLMProvider
    api_key: SecretStr
    model_name: str


class ClaudeLLMSettings(FrozenModelSettings):
    provider: Providers.LLMProvider
    model_name: str
    api_key: SecretStr

type LLMSettings = GeminiLLMSettings | OpenAILLMSettings | ClaudeLLMSettings

type LLMCatalog = Mapping[str, LLMSettings]
