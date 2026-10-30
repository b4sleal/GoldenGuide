"""Configuration the embedding service loads: its own connection limits and the local model catalogs."""
from pydantic import BaseModel, ConfigDict

from goldenguide_common.contracts.embedding_models import (
    LocalEmbeddingCatalog,
    LocalEmbeddingServiceSettings,
    LocalRerankerCatalog,
    LocalSparseVectorizerCatalog,
)


class LocalEmbeddingServiceConfig(BaseModel):
    """The subset ConfigLoader passes to the embedding process, without unrelated API settings."""

    model_config = ConfigDict(frozen=True)

    settings: LocalEmbeddingServiceSettings
    local_embedding: LocalEmbeddingCatalog
    local_sparse_vectorizer: LocalSparseVectorizerCatalog
    local_reranker: LocalRerankerCatalog
