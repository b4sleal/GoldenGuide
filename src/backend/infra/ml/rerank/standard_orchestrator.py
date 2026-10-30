"""Reranker orchestrator: route to the adapter named by the reranker profile."""
from backend.domain.ports.providers.reranker import Reranker
from backend.domain.settings.profiles import RerankerProfile


class StandardRerankerOrchestrator:
    def __init__(self, reranker_providers: dict[str, Reranker]):
        self.reranker_providers = reranker_providers

    async def rerank(self, query: str, documents: list[str], profile: RerankerProfile) -> list[float]:
        return await self.reranker_providers[profile.primary.name].rerank(query, documents)
