"""Sparse (SPLADE-style) vectorizer port for hybrid search."""
from typing import Protocol

from goldenguide_common.contracts.vectors import SparseVector
from backend.domain.settings.profiles import SparseVectorProfile


class SparseVectorizer(Protocol):
    async def vectorize_query(self, text: str) -> SparseVector:
        ...

    async def vectorize_documents(self, texts: list[str]) -> list[SparseVector]:
        ...

class SparseVectorizerOrchestrator:
    async def vectorize_query(self, text: str, profile: SparseVectorProfile) -> SparseVector:
        ...

    async def vectorize_documents(self, texts: list[str], profile: SparseVectorProfile) -> list[SparseVector]:
        ...