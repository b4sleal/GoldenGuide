"""Sparse vectorizer orchestrator: route to the adapter named by the sparse profile."""
from backend.domain.settings.profiles import SparseVectorProfile
from goldenguide_common.contracts.vectors import SparseVector
from backend.domain.ports.providers.sparse import SparseVectorizer


class StandardSparseVectorizerOrchestrator:
    def __init__(self, vectorizer_providers: dict[str, SparseVectorizer]):
        self.vectorizer_providers = vectorizer_providers

    async def vectorize_query(self, text: str, profile: SparseVectorProfile) -> SparseVector:
        return await self.vectorizer_providers[profile.primary.name].vectorize_query(text)

    async def vectorize_documents(self, texts: list[str], profile: SparseVectorProfile) -> list[SparseVector]:
        return await self.vectorizer_providers[profile.primary.name].vectorize_documents(texts)