"""ML wiring: LLM, embedding, sparse, reranker and text-splitter adapters from the provider catalog,
each behind its orchestrator (profile-based selection with fallback).
"""
from dependency_injector import containers, providers

import backend.domain.common.providers_enum as Providers
from backend.core.factories.resolver import merge_provider_maps, resolve_catalog_items
from backend.infra.ml.embeddings.standard_orchestrator import (
    StandardEmbeddingOrchestrator,
)
from backend.infra.ml.llms.standard_orchestrator import StandardLLMOrchestrator
from backend.infra.ml.rerank.standard_orchestrator import StandardRerankerOrchestrator
from backend.infra.ml.sparse.standard_orchestrators import (
    StandardSparseVectorizerOrchestrator,
)
from backend.infra.ml.text.standard_orchestrator import StandardTextSplitterOrchestrator


class MLContainer(containers.DeclarativeContainer):

    catalog = providers.Dependency()
    local_embedding_service = providers.Dependency()

    # ---------- LLM + Embedding ----------
    llm_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.llm,
        provider_enum=Providers.LLMProvider
    )

    cloud_embedding_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.embedding,
        provider_enum=Providers.EmbeddingProvider
    )

    local_embedding_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.local_embedding,
        provider_enum=Providers.EmbeddingProvider,
        service_settings=local_embedding_service,
    )

    embedding_providers = providers.Singleton(
        merge_provider_maps,
        cloud_embedding_providers,
        local_embedding_providers,
    )

    llm_orchestrator = providers.Singleton(
        StandardLLMOrchestrator,
        llm_providers=llm_providers
    )

    embedding_orchestrator = providers.Singleton(
        StandardEmbeddingOrchestrator,
        embedding_providers=embedding_providers
    )

    # ---------- Sparse Vectorizer ----------

    local_sparse_vectorizer_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.local_sparse_vectorizer,
        provider_enum=Providers.LocalSparseVectorizerProvider,
        service_settings=local_embedding_service
    )

    sparse_vectorizer_orchestrator = providers.Singleton(
        StandardSparseVectorizerOrchestrator,
        vectorizer_providers=local_sparse_vectorizer_providers
    )

    # ---------- Reranker ----------

    local_reranker_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.local_reranker,
        provider_enum=Providers.LocalRerankerProvider,
        service_settings=local_embedding_service,
    )

    reranker_orchestrator = providers.Singleton(
        StandardRerankerOrchestrator,
        reranker_providers=local_reranker_providers,
    )


    # ---------- Text Processing ----------

    text_splitter_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.text_splitter,
        provider_enum=Providers.TextSplitterProvider
    )

    text_splitter_orchestrator = providers.Singleton(
        StandardTextSplitterOrchestrator,
        text_splitter_providers=text_splitter_providers
    )