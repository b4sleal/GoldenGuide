"""Provider names selectable in configuration (LLM, embeddings, stores, ...) and the active-instance keys.

Each value must have a factory in core/factories/registry.py.
"""
from enum import StrEnum

from goldenguide_common.contracts.embedding_models import (
    LocalEmbeddingProvider,
    LocalRerankerProvider,
    LocalSparseVectorizerProvider,
)


class BlobStorageProvider(StrEnum):
    MINIO = "minio"
    S3 = "s3"

class VectorStoreProvider(StrEnum):
    QDRANT = "qdrant"

class CacheProvider(StrEnum):
    REDIS = "redis"

class TextSplitterProvider(StrEnum):
    LANGCHAIN_RECURSIVE= "lc-recursive-text-splitter"

class DBProvider(StrEnum):
    POSTGRES = "postgres"


class LLMProvider(StrEnum):
    GEMINI = "gemini"
    OPENAI = "openai"
    CLAUDE = "claude"

class EmbeddingProvider(StrEnum):
    GEMINI = "gemini"
    OPENAI = "openai"
    LOCAL = "local"

class SparseVectorizerProvider(StrEnum):
    LOCAL = "local"


class ActiveBlobStorage(StrEnum):
    APP = "app"

class ActiveDB(StrEnum):
    APP = "app"
    SCHOOL = "school"

class ActiveCache(StrEnum):
    APP = "app"

class ActiveVectorStore(StrEnum):
    APP = "app"

PROVIDER_NAMESPACE = {
    BlobStorageProvider: "blob_storage",
    VectorStoreProvider: "vector_store",
    CacheProvider: "cache",
    TextSplitterProvider: "text_splitter",
    DBProvider: "db",

    LLMProvider: "llm",
    EmbeddingProvider: "embedding",
    SparseVectorizerProvider: "sparse_vectorizer",
    LocalEmbeddingProvider: "local_embedding",
    LocalSparseVectorizerProvider: "local_sparse_vectorizer",
    LocalRerankerProvider: "local_reranker",
}