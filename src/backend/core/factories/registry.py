"""Which adapter class implements each configured provider, and which repositories each database exposes.

Adding a provider: implement the adapter in infra, add its enum value, register it here.
"""
from backend.infra.persistence.db.app.base.settings_repo import SqlSettingsRepository
from backend.infra.persistence.db.app.base.document_repo import SqlDocumentRepository
from backend.infra.persistence.db.app.base.conversation_repo import SqlConversationRepository
from backend.infra.persistence.db.app.base.job_repo import SqlJobRepository
from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps
from backend.domain.common import providers_enum as Providers

from backend.core.factories.factory import build_from_settings, build_from_settings_local, build_repo_bundle
from backend.domain.common.providers_enum import PROVIDER_NAMESPACE


from backend.infra.persistence.blob_storage.minio import MinIOStorage
from backend.infra.persistence.caching.redis import RedisCache
from backend.infra.persistence.db.db_connection import DatabaseConnection
from backend.infra.persistence.vectors.qdrant.store import QDrantStore

from backend.infra.ml.embeddings.gemini import GeminiEmbedding
from backend.infra.ml.embeddings.openai import OpenAIEmbedding
from backend.infra.ml.embeddings.local import LocalEmbedding
from backend.infra.ml.llms.claude import ClaudeLLM
from backend.infra.ml.llms.gemini import GeminiLLM
from backend.infra.ml.llms.openai import OpenAILLM
from backend.infra.ml.rerank.local import LocalReranker
from backend.infra.ml.sparse.local import LocalSparseVectorizer
from backend.infra.ml.text.recursive_splitter import RecursiveTextSplitter

from backend.infra.persistence.db.school.base.wlu_page_repo import SqlWluPageRepository
from backend.infra.persistence.db.school.base.course_page_repo import SqlCourseRepository
from backend.infra.persistence.db.school.base.course_term_repo import SqlCourseTermRepository
from backend.infra.persistence.db.school.base.scraping_repo import SqlScrapingRepository


PROVIDER_REGISTRY = {
    PROVIDER_NAMESPACE[Providers.BlobStorageProvider]: {
        Providers.BlobStorageProvider.MINIO: build_from_settings(MinIOStorage),
    },
    PROVIDER_NAMESPACE[Providers.CacheProvider]: {
        Providers.CacheProvider.REDIS: build_from_settings(RedisCache),
    },
    PROVIDER_NAMESPACE[Providers.DBProvider]: {
        Providers.DBProvider.POSTGRES: build_from_settings(DatabaseConnection),
    },
    PROVIDER_NAMESPACE[Providers.VectorStoreProvider]: {
        Providers.VectorStoreProvider.QDRANT: build_from_settings(QDrantStore),
    },
    PROVIDER_NAMESPACE[Providers.LLMProvider]: {
        Providers.LLMProvider.GEMINI: build_from_settings(GeminiLLM),
        Providers.LLMProvider.OPENAI: build_from_settings(OpenAILLM),
        Providers.LLMProvider.CLAUDE: build_from_settings(ClaudeLLM),
    },
    PROVIDER_NAMESPACE[Providers.EmbeddingProvider]: {
        Providers.EmbeddingProvider.GEMINI: build_from_settings(GeminiEmbedding),
        Providers.EmbeddingProvider.OPENAI: build_from_settings(OpenAIEmbedding),
        Providers.LocalEmbeddingProvider.MINILM: build_from_settings_local(LocalEmbedding),
        Providers.LocalEmbeddingProvider.FASTEMBED_COLBERT: build_from_settings_local(LocalEmbedding),
    },
    PROVIDER_NAMESPACE[Providers.LocalSparseVectorizerProvider]: {
        Providers.LocalSparseVectorizerProvider.SPLADE: build_from_settings_local(LocalSparseVectorizer),
    },
    PROVIDER_NAMESPACE[Providers.LocalRerankerProvider]: {
        Providers.LocalRerankerProvider.CROSS_ENCODER: build_from_settings_local(LocalReranker),
    },
    PROVIDER_NAMESPACE[Providers.TextSplitterProvider]: {
        Providers.TextSplitterProvider.LANGCHAIN_RECURSIVE: build_from_settings(RecursiveTextSplitter),
    }
}

# One stateless dialect implementation per database provider; every repository shares it.
POSTGRES_OPS = PostgresDialectOps()

APP_REPO_REGISTRY = {
    Providers.DBProvider.POSTGRES: build_repo_bundle(
        documents=lambda session: SqlDocumentRepository(session, POSTGRES_OPS),
        settings=lambda session: SqlSettingsRepository(session),
        jobs=lambda session: SqlJobRepository(session, POSTGRES_OPS),
        conversations=lambda session: SqlConversationRepository(session, POSTGRES_OPS),
    ),
}

SCHOOL_REPO_REGISTRY = {
    Providers.DBProvider.POSTGRES: build_repo_bundle(
        courses=lambda session: SqlCourseRepository(session, POSTGRES_OPS),
        wlu_pages=lambda session: SqlWluPageRepository(session, POSTGRES_OPS),
        course_terms=lambda session: SqlCourseTermRepository(session, POSTGRES_OPS),
        scraping=lambda session: SqlScrapingRepository(session, POSTGRES_OPS),
    ),
}
