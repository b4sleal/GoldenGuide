"""Vector store port (Qdrant today): collections, upsert/delete, hybrid search and filter-based cleanup."""
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from backend.domain.ports.providers.vector_store.vector_models import (
    CollectionMetadata,
    PayloadIndexKind,
    VectorPayloadField,
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

    async def set_payload(
            self,
            name: str,
            filters: dict,
            values: dict[str, Any],
            remove: list[str],
    ) -> None:
        """On every point matching `filters`, set `values` and delete the `remove` keys; vectors and
        other keys are untouched. Like delete, an empty filter is refused (it would match everything)."""
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

    async def ensure_payload_indexes(
            self,
            name: str,
            fields: Mapping[VectorPayloadField, PayloadIndexKind],
    ) -> list[VectorPayloadField]:
        """Index each of `fields` that is not indexed yet and return those created. Idempotent; a field
        already indexed with a different kind raises instead of replacing that index."""
        ...