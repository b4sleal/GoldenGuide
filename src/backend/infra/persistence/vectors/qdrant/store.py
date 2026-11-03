"""Qdrant adapter: collections with named vectors ("dense", "sparse", "colbert"), batched upserts,
hybrid search (dense + sparse fused with Reciprocal Rank Fusion, then reranked by ColBERT), and
filter-based deletes.
"""
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import structlog

from qdrant_client import AsyncQdrantClient, models
from qdrant_client.http.models import (
    Distance,
    PayloadSchemaType,
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
    PayloadIndexKind,
    RetrievedChunk,
    VectorPayloadField,
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
# ColBERT only reranks candidates found by dense/sparse search, so it needs no HNSW graph. Building
# one over every token vector costs hours of optimizer CPU for nothing.
RERANK_ONLY_HNSW = models.HnswConfigDiff(m=0)
PAYLOAD_SCHEMA_TYPES = {
    PayloadIndexKind.KEYWORD: PayloadSchemaType.KEYWORD,
    PayloadIndexKind.DATETIME: PayloadSchemaType.DATETIME,
}


class QDrantStore:
    def __init__(self, settings: QdrantSettings):
        self.client = AsyncQdrantClient(
            host=settings.host,
            port=settings.port,
            grpc_port=settings.grpc_port,
            prefer_grpc=settings.prefer_grpc,
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
                hnsw_config=RERANK_ONLY_HNSW,
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

    async def ensure_payload_indexes(
            self,
            name: str,
            fields: Mapping[VectorPayloadField, PayloadIndexKind],
    ) -> list[VectorPayloadField]:
        # Qdrant builds a new index from the points already stored, so this also migrates
        # existing collections. Existing indexes are read first so a type mismatch is never
        # silently replaced and repeated startups make no changes.
        existing = (await self.client.get_collection(name)).payload_schema or {}
        created = []
        for field, kind in fields.items():
            schema = PAYLOAD_SCHEMA_TYPES[kind]
            current = existing.get(field.value)
            if current is not None:
                if current.data_type != schema:
                    raise RuntimeError(
                        f'Collection "{name}" indexes payload field "{field}" as {current.data_type}, '
                        f"expected {schema}. Drop that index or migrate the collection."
                    )
                continue
            await self.client.create_payload_index(
                collection_name=name, field_name=field.value, field_schema=schema, wait=True,
            )
            created.append(field)
        if created:
            logger.info("qdrant_payload_indexes_created", collection=name, fields=[f.value for f in created])
        return created

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

        # Candidates come from dense and sparse search. Each prefetch is filtered itself: the outer
        # filter alone would only discard candidates picked from the whole collection.
        candidates = []
        if dense_vector is not None:
            candidates.append(
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    filter=q_filter,
                    limit=prefetch_limit,
                )
            )
        if sparse_vector is not None:
            candidates.append(
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vector.indices,
                        values=sparse_vector.values,
                    ),
                    using="sparse",
                    filter=q_filter,
                    limit=prefetch_limit,
                )
            )
        rrf = models.RrfQuery(rrf=models.Rrf(k=RRF_K))

        if multivector is not None:
            # ColBERT reranks the (fused) candidates. Without candidates it scores every point,
            # since its vectors have no HNSW index (RERANK_ONLY_HNSW).
            query, using = multivector, "colbert"
            if len(candidates) > 1:
                prefetch = [models.Prefetch(prefetch=candidates, query=rrf, limit=prefetch_limit)]
            else:
                prefetch = candidates or None
        elif len(candidates) == 1:
            query, using, prefetch = candidates[0].query, candidates[0].using, None
        elif candidates:
            query, using, prefetch = rrf, None, candidates
        else:
            raise ValueError("Search requires at least one vector type.")

        results = await self.client.query_points(
            collection_name=name,
            prefetch=prefetch,
            query=query,
            using=using,
            limit=limit,
            query_filter=q_filter,
            score_threshold=score_threshold,
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

    async def set_payload(
            self,
            name: str,
            filters: dict,
            values: dict[str, Any],
            remove: list[str],
    ) -> None:
        q_filter = self._required_filter(filters)
        if values:
            await self.client.set_payload(collection_name=name, payload=values, points=q_filter, wait=True)
        if remove:
            await self.client.delete_payload(collection_name=name, keys=remove, points=q_filter, wait=True)

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
        """The filter for a delete or payload change. An empty one (or only None values) would match the
        whole collection."""
        q_filter = self._build_filter(filters)
        if q_filter is None:
            raise ValueError(f"Refusing to change points without a filter (got {filters!r})")
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