"""Typed settings for embedding, sparse vectorizer and reranker providers (cloud and local service)."""
from collections.abc import Mapping

from pydantic import SecretStr

from backend.domain.common import providers_enum as Providers
from goldenguide_common.contracts.embedding_models import (
    FrozenModelSettings,
    LocalEmbeddingSettings,
    LocalSparseVectorizerSettings,
)


class OpenAIEmbeddingSettings(FrozenModelSettings):
    provider: Providers.EmbeddingProvider
    model_name: str
    dimension: int
    api_key: SecretStr


class GeminiEmbeddingSettings(FrozenModelSettings):
    provider: Providers.EmbeddingProvider
    model_name: str
    dimension: int
    api_key: SecretStr

type SparseVectorizerSettings = LocalSparseVectorizerSettings

type EmbeddingSettings = OpenAIEmbeddingSettings | GeminiEmbeddingSettings | LocalEmbeddingSettings

type EmbeddingCatalog = Mapping[str, EmbeddingSettings]
