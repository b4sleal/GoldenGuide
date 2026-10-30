"""Application-facing vector store: delegates to the configured adapter and adds timing/cleanup logs.

Errors propagate unlogged; callers log them with record context (ingestion) or fall back (retrieval).
"""
import time
from datetime import datetime

import structlog

from backend.domain.ports.providers.vector_store.port import VectorStore
from goldenguide_common.contracts.vectors import DenseVector, MultiVector, SparseVector
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk, VectorPoint

logger = structlog.get_logger()


class AppVectorStore:

    def __init__(self, vector_store: VectorStore):
        self.vector_store = vector_store

    async def upsert(
            self,
            name: str,
            points: list[VectorPoint]
    ):
        start = time.perf_counter()

        await self.vector_store.upsert(
            name=name,
            points=points
        )

        # Per record during embedding jobs, so debug level; the job logs progress per batch.
        logger.debug(
            "qdrant_upsert_completed",
            collection=name,
            points=len(points),
            elapsed_seconds=round(time.perf_counter() - start, 3),
        )

    async def search(
            self,
            name: str,
            dense_vector: DenseVector | None = None,
            sparse_vector: SparseVector | None = None,
            multivector: MultiVector | None = None,
            limit: int = 50,
            filters: dict | None = None,
            score_threshold: float | None = None
    ) -> list[RetrievedChunk]:
        return await self.vector_store.search(
            name=name,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            multivector=multivector,
            limit=limit,
            filters=filters,
            score_threshold=score_threshold
        )

    async def delete(
            self,
            name: str,
            filters: dict
    ):
        await self.vector_store.delete(
            name=name,
            filters=filters
        )

    async def delete_older_than(
            self,
            name: str,
            filters: dict,
            timestamp_field: str,
            before: datetime,
    ) -> int:
        deleted = await self.vector_store.delete_older_than(
            name=name,
            filters=filters,
            timestamp_field=timestamp_field,
            before=before,
        )
        logger.info("qdrant_stale_points_deleted", collection=name, filters=filters, before=before.isoformat(), deleted=deleted)
        return deleted

    async def search_by_filter(
            self,
            name: str,
            filters: dict,
            limit: int = 10000
    ):
        return await self.vector_store.search_by_filter(
            name=name,
            filters=filters,
            limit=limit
        )
