"""Vector store port (Qdrant today): collections, upsert/delete, hybrid search and filter-based cleanup."""
from datetime import datetime
from typing import Any, Protocol

from backend.domain.ports.providers.vector_store.vector_models import (
    CollectionMetadata,
    RetrievedChunk,
    VectorPoint,
)
from goldenguide_common.contracts.vectors import DenseVector, MultiVector, SparseVector
from backend.domain.settings.profiles import VectorCollectionSettings


class VectorStore(Protocol):
    async def upsert(
            self,
            name: str,
            points: list[VectorPoint]
    ) -> None:
        ...

    async def search(
            self,
            name: str,
            dense_vector: DenseVector | None = None,
            sparse_vector: SparseVector | None = None,
            multivector: MultiVector | None = None,
            limit: int = 50,
            filters: dict | None = None,
            score_threshold: float | None = None,
    ) -> list[RetrievedChunk]:
        ...

    async def delete(
            self,
            name: str,
            filters: dict
    ) -> None:
        ...

    async def search_by_filter(
            self,
            name: str,
            filters: dict,
            limit: int = 10000
    ) -> list[Any]:
        ...

    async def delete_older_than(
            self,
            name: str,
            filters: dict,
            timestamp_field: str,
            before: datetime,
    ) -> int:
        """Delete points matching `filters` whose `timestamp_field` is earlier than `before`; return how many."""
        ...

class ManagedVectorStore(VectorStore, Protocol):
    async def get_collection_metadata(self, name: str):
        ...

    async def collection_exists(self, name: str) -> bool:
        ...

    async def create_collection(
            self,
            name: str,
            config: VectorCollectionSettings,
            metadata: CollectionMetadata
    ) -> str:
        ...