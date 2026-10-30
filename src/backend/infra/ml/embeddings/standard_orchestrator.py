"""Embedding orchestrator: route embedding calls to the adapter named by the embedding profile.

Errors propagate to the caller, which logs them with its own context (ingestion record, retrieval
profile); logging here too would only duplicate each failure.
"""
from collections.abc import Mapping

from backend.domain.ports.providers.embedding import Embedding
from backend.domain.settings.profiles import EmbeddingProfile


class StandardEmbeddingOrchestrator:

    def __init__(
            self,
            embedding_providers: Mapping[str, Embedding]
    ):
        self.embedding_providers = embedding_providers

    def _provider(self, profile: EmbeddingProfile) -> Embedding:
        name = profile.primary.name
        provider = self.embedding_providers.get(name)
        if provider is None:
            raise LookupError(f"Embedding provider '{name}' is not configured")
        return provider

    async def embed_documents(
            self,
            texts: list[str],
            profile: EmbeddingProfile
    ):
        return await self._provider(profile).embed_documents(texts)

    async def embed_query(
            self,
            text: str,
            profile: EmbeddingProfile
    ):
        return await self._provider(profile).embed_query(text)
