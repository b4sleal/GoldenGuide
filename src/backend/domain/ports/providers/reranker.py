"""Cross-encoder reranker port: one relevance score per document, in input order."""
from typing import Protocol

from backend.domain.settings.profiles import RerankerProfile


class Reranker(Protocol):
    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Relevance score of each document for `query`, in the documents' order (higher is better)."""
        ...

class RerankerOrchestrator(Protocol):
    async def rerank(self, query: str, documents: list[str], profile: RerankerProfile) -> list[float]:
        ...
