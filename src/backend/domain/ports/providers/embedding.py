"""Dense / multi-vector embedding port, selected by embedding profile."""
from typing import Protocol

from goldenguide_common.contracts.vectors import EmbeddingVector
from backend.domain.settings.profiles import EmbeddingProfile


class Embedding(Protocol):
    async def embed_query(self, text: str) -> EmbeddingVector:
        ...

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        ...

class EmbeddingOrchestrator(Protocol):
    async def embed_query(self, text: str, profile: EmbeddingProfile): ...
    async def embed_documents(self, texts: list[str], profile: EmbeddingProfile): ...
