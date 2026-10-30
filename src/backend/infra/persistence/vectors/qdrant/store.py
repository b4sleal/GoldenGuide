"""Qdrant adapter: collections with named vectors ("dense", "sparse", "colbert"), batched upserts,
hybrid search fused with Reciprocal Rank Fusion, and filter-based deletes.
"""
from datetime import datetime

import structlog

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVector as QDrantSparseVector,
    SparseVectorParams,
    VectorParams,
)
from qdrant_client.models import FieldCondition, Filter, MatchValue

from backend.domain.settings.profiles import VectorCollectionSettings
from goldenguide_common.contracts.vectors import DenseVector, MultiVector, SparseVector
from backend.domain.ports.providers.vector_store.vector_models import (
    CollectionMetadata,
    RetrievedChunk,
    VectorPoint,
)
from backend.domain.settings.providers import QdrantSettings
from backend.shared.utils.size_batching import batch_by_size
from backend.infra.persistence.vectors.qdrant.serialization import (
    qdrant_point_size,
)

logger = structlog.get_logger()

# Upsert requests are cut well below Qdrant's request size limit, leaving room for JSON framing.
MAX_UPSERT_BYTES = 8 * 1024 * 1024
UPSERT_SAFETY_FACTOR = 0.75
UPSERT_REQUEST_OVERHEAD_BYTES = 1024
# Reciprocal Rank Fusion constant: higher values flatten the advantage of top ranks.
RRF_K = 60


class QDrantStore:
    def __init__(self, settings: QdrantSettings):
        self.client = AsyncQdrantClient(
            host=settings.host,
            port=settings.port,
            api_key=settings.api_key.get_secret_value(),
            https=settings.https,
            timeout=settings.timeout_seconds,
        )

    # --------------------------------------------------
    # Collection Management
    # --------------------------------------------------
    async def get_collection_metadata(self, name: str) -> CollectionMetadata:
        collection = await self.client.get_collection(name)
        metadata = collection.config.metadata
        return CollectionMetadata.model_validate(metadata)

    async def collection_exists(self, name: str) -> bool:
        return await self.client.collection_exists(name)

    async def create_collection(
            self,
            name: str,
            config: VectorCollectionSettings,
            metadata: CollectionMetadata,
    ) -> None:
        logger.info("qdrant_create_collection", collection=name)

        vectors_config = {}

        if config.vectors.dense:
            vectors_config["dense"] = VectorParams(
                size=metadata.embedding_dimension,
                distance=Distance.COSINE,
            )

        if config.vectors.multi_vector:
            vectors_config["colbert"] = VectorParams(
                size=config.vectors.multi_vector.size,
                distance=Distance.COSINE,
                multivector_config=models.MultiVectorConfig(
                    comparator=models.MultiVectorComparator.MAX_SIM
                ),
            )

        sparse_config = None
        if config.vectors.sparse:
            sparse_config = {
                "sparse": SparseVectorParams(
                    index=SparseIndexParams(on_disk=False)
                )
            }

        await self.client.create_collection(
            collection_name=name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_config,
            metadata=metadata.model_dump(),
        )

    # --------------------------------------------------
    # Upsert
    # --------------------------------------------------
    async def upsert(self, name: str, points: list[VectorPoint]) -> None:
        if not points:
            return

        qdrant_points: list[PointStruct] = []

        for p in points:
            all_vectors = {}

            if p.dense_vector is not None:
                all_vectors["dense"] = p.dense_vector

            if p.multi_vector is not None:
                all_vectors["colbert"] = p.multi_vector

            if p.sparse_vector is not None:
                all_vectors["sparse"] = QDrantSparseVector(
                    indices=p.sparse_vector.indices,
                    values=p.sparse_vector.values,
                )

            qdrant_points.append(
                PointStruct(
                    id=p.id,
                    vector=all_vectors,
                    payload=dict(p.payload or {}),
                )
            )

        for batch in batch_by_size(
                items=qdrant_points,
                max_bytes=int(MAX_UPSERT_BYTES * UPSERT_SAFETY_FACTOR),
                size_of=qdrant_point_size,
                overhead=UPSERT_REQUEST_OVERHEAD_BYTES,
        ):
            await self.client.upsert(
                collection_name=name,
                points=batch,
                wait=True,
            )

    # --------------------------------------------------
    # Search
    # --------------------------------------------------

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

        q_filter = self._build_filter(filters)
        prefetch_limit = max(limit * 5, 200)
        prefetch_tasks = []

        # 1. Queue the Dense search
        if dense_vector is not None:
            prefetch_tasks.append(
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=prefetch_limit,
                )
            )

        # 2. Queue the Sparse search
        if sparse_vector is not None:
            prefetch_tasks.append(
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector.indices,
                        values=sparse_vector.values
                    ),
                    using="sparse",
                    limit=prefetch_limit,
                )
            )

        # 3. Queue the ColBERT search
        if multivector is not None:
            prefetch_tasks.append(
                models.Prefetch(
                    # For Prefetch, pass the 2D list directly, 'using' tells Qdrant it's ColBERT
                    query=multivector,
                    using="colbert",
                    limit=prefetch_limit,
                )
            )

        if not prefetch_tasks:
            raise ValueError("Search requires at least one vector type.")

        # 4. If only ONE vector type was passed, just do a standard query
        if len(prefetch_tasks) == 1:
            results = await self.client.query_points(
                collection_name=name,
                query=prefetch_tasks[0].query,
                using=prefetch_tasks[0].using,
                limit=limit,
                query_filter=q_filter,
                score_threshold=score_threshold,
                with_payload=True,
                with_vectors=False,
            )
            return self._convert_results(results)

        # 5. If MULTIPLE vectors were passed, fuse them with RRF
        results = await self.client.query_points(
            collection_name=name,
            prefetch=prefetch_tasks,
            query=models.RrfQuery(rrf=models.Rrf(k=RRF_K)),
            limit=limit,
            query_filter=q_filter,
            with_payload=True,
            with_vectors=False,
        )

        return self._convert_results(results)

    # --------------------------------------------------
    # Delete
    # --------------------------------------------------

    async def delete(self, name: str, filters: dict) -> None:
        q_filter = self._required_filter(filters)

        await self.client.delete(
            collection_name=name,
            points_selector=q_filter,
            wait=True,
        )

    async def delete_older_than(
            self,
            name: str,
            filters: dict,
            timestamp_field: str,
            before: datetime,
    ) -> int:
        q_filter = Filter(must=[
            *self._required_filter(filters).must,
            FieldCondition(key=timestamp_field, range=models.DatetimeRange(lt=before)),
        ])

        stale = (await self.client.count(collection_name=name, count_filter=q_filter, exact=True)).count
        if stale:
            await self.client.delete(collection_name=name, points_selector=q_filter, wait=True)
        return stale

    # --------------------------------------------------
    # Scroll
    # --------------------------------------------------

    async def search_by_filter(
            self,
            name: str,
            filters: dict,
            limit: int = 10000,
    ):
        q_filter = self._build_filter(filters)

        results, _ = await self.client.scroll(
            collection_name=name,
            scroll_filter=q_filter,
            limit=limit,
            with_payload=True,
        )

        return results

    async def shutdown(self) -> None:
        await self.client.close()

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _required_filter(self, filters: dict | None) -> Filter:
        """The filter for a delete. An empty one (or only None values) would match the whole collection."""
        q_filter = self._build_filter(filters)
        if q_filter is None:
            raise ValueError(f"Refusing to delete without a filter (got {filters!r})")
        return q_filter

    def _build_filter(self, filters: dict | None) -> Filter | None:
        """Exact-match conditions for every non-None value; None when nothing is left to filter on."""
        if not filters:
            return None

        conditions = [
            FieldCondition(key=k, match=MatchValue(value=v))
            for k, v in filters.items()
            if v is not None
        ]

        return Filter(must=conditions) if conditions else None

    def _convert_results(self, results) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                content=p.payload.get("text", "") if p.payload else "",
                score=p.score,
                payload=p.payload,
            )
            for p in results.points
        ]