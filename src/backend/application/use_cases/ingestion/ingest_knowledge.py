"""Embed one knowledge record (course, course term, page or document) into its vector collection(s).

Text: YAML templates (text_enrichment) render a header/prefix, the body is split into chunks, and each
chunk is embedded with every vector type the collection has (dense, sparse, multi-vector). Chunks are
embedded and written in slices, so memory per record is bounded by the slice size, not the record size.
A record's earlier points are deleted only after every slice was written; after a failure the old points
remain (possibly next to some new ones) and the next successful run removes them.
"""
from datetime import datetime, timezone
from string import Formatter

import structlog

from backend.domain.entities.ingestion_types import KnowledgeVectorPayload, KnowledgeSourceType, VectorSource
from backend.domain.settings.profiles import VectorCollectionSettings, VectorCollectionCatalog
from backend.domain.ports.providers.vector_store.vector_models import VectorPayloadField, VectorPoint
from backend.domain.ports.providers.sparse import SparseVectorizerOrchestrator
from backend.domain.ports.providers.text_splitter import TextSplitterOrchestrator
from backend.domain.ports.providers.vector_store.port import VectorStore
from backend.domain.ports.providers.embedding import EmbeddingOrchestrator
from backend.shared.utils.hashing import compute_uuid

logger = structlog.get_logger()

# The vector collection profile ingestion writes to (configs/catalogs/profiles/vector_collection.yml).
TARGET_COLLECTION_PROFILE = "multi_sparse"


class KnowledgeIngestor:
    def __init__(
            self,
            vector_collections: VectorCollectionCatalog,
            vector_store: VectorStore,
            embedding_orchestrator: EmbeddingOrchestrator,
            sparse_vectorizer_orchestrator: SparseVectorizerOrchestrator,
            text_splitter_orchestrator: TextSplitterOrchestrator,
    ):
        self.vector_collections = vector_collections
        self.vector_store = vector_store
        self.embedding = embedding_orchestrator
        self.sparse = sparse_vectorizer_orchestrator
        self.text_splitter = text_splitter_orchestrator

    def _target_profiles(self) -> list[VectorCollectionSettings]:
        return [profile for _, profile in self.vector_collections.items() if profile.name == TARGET_COLLECTION_PROFILE]

    async def ingest(self, payload: KnowledgeVectorPayload):
        """Embed `payload` into every target collection. Errors propagate; callers log them with record context."""
        results = []
        for profile in self._target_profiles():
            results.append(await self.ingest_profile(payload, profile))
        return {"targets": len(results), "skipped": sum(r["skipped"] for r in results)}

    async def refresh_payload(self, payload: KnowledgeVectorPayload) -> None:
        """Rewrite `payload`'s fields on the record's existing points without embedding again.

        For payload-only changes (a new or changed filter field): vectors, chunk text and the embed
        timestamps stay as they are, so stale-vector cleanup still sees when each point was embedded.
        Fields that are now None are removed, as a re-embed would leave them out. A record that was
        never embedded has no points, and stays that way until it is.
        """
        fields = payload.model_dump(exclude={"content"}, mode="json")
        values = {key: value for key, value in fields.items() if value is not None}
        removed = [key for key, value in fields.items() if value is None]
        for profile in self._target_profiles():
            await self.vector_store.set_payload(
                name=profile.key,
                filters={VectorPayloadField.SOURCE_ID: payload.source_id},
                values=values,
                remove=removed,
            )

    async def delete_stale(self, source: VectorSource, embedded_before: datetime) -> int:
        """Delete `source`'s vectors last embedded before `embedded_before`: records a fresh run no longer has."""
        deleted = 0
        for profile in self._target_profiles():
            deleted += await self.vector_store.delete_older_than(
                name=profile.key,
                filters={VectorPayloadField.EMBEDDING_SOURCE: source.value},
                timestamp_field=VectorPayloadField.UPDATED_AT,
                before=embedded_before,
            )
        return deleted

    async def _created_at(self, collection_name: str, source_id: str, now: str) -> str:
        """Keep the first-embedded time across re-embeds; a new record starts now."""
        existing = await self.vector_store.search_by_filter(
            name=collection_name, filters={VectorPayloadField.SOURCE_ID: source_id}, limit=1,
        )
        return (existing[0].payload or {}).get(VectorPayloadField.CREATED_AT, now) if existing else now

    async def ingest_profile(self, payload: KnowledgeVectorPayload, profile: VectorCollectionSettings):
        """Chunk, embed and replace `payload`'s points in one collection."""
        collection_name = profile.key
        templates = profile.text_enrichment.get(payload.source_type, {}).get(payload.record_type, [])
        is_course = (
                payload.record_type == KnowledgeSourceType.COURSE.value
                and payload.source_type in {
                    KnowledgeSourceType.WLU_PAGE,
                    KnowledgeSourceType.LORIS_REGISTRATION,
                }
        )

        if is_course:
            if not templates:
                raise ValueError(
                    f"Missing embedding template: "
                    f"{payload.source_type}/{payload.record_type}"
                )

            # The first YAML entry is the repeated course identifier.
            header = self._render_template(templates[:1], payload)

            # The remaining entries contain the course information.
            body = self._render_template(templates[1:], payload)

            if not header:
                raise ValueError(
                    f"Missing course chunk header for {payload.source_id}"
                )

            # Reserve space for the repeated header.
            chunk_size = profile.chunking.chunk_size
            available_size = chunk_size - len(header) - 2

            if available_size <= 0:
                raise ValueError(
                    f"Course header exceeds configured chunk size: "
                    f"{payload.source_id}"
                )

            adjusted_chunking = profile.chunking.model_copy(
                update={"chunk_size": available_size}
            )

            if body:
                raw_chunks = self.text_splitter.split(
                    body, adjusted_chunking
                )
                chunks = [
                    f"{header}\n\n{chunk}"
                    for chunk in raw_chunks
                    if chunk.strip()
                ]
            else:
                chunks = [header]

        else:
            # WLU pages and documents: the rendered template is a prefix on every chunk.
            prefix = self._render_template(templates, payload)

            raw_chunks = self.text_splitter.split(
                payload.content, profile.chunking
            )

            chunks = [
                f"{prefix}\n\n{chunk}" if prefix else chunk
                for chunk in raw_chunks
            ]

        run_started = datetime.now(timezone.utc)
        now = run_started.isoformat()
        base_payload = {
            **payload.model_dump(exclude={"content"}, exclude_none=True, mode="json"),
            VectorPayloadField.CREATED_AT: await self._created_at(collection_name, payload.source_id, now),
            VectorPayloadField.UPDATED_AT: now,
        }
        slice_size = profile.ingest_chunks_per_slice
        for start in range(0, len(chunks), slice_size):
            points = await self._embed_slice(
                profile, payload.source_id, chunks[start:start + slice_size], start, base_payload,
            )
            await self.vector_store.upsert(name=collection_name, points=points)

        # Only after every slice is written: drop this record's points from earlier runs (changed or
        # removed chunks; unchanged chunks share their id and were overwritten). A failed slice skips
        # this, so old points stay next to the slices already written until the next successful run.
        await self.vector_store.delete_older_than(
            name=collection_name,
            filters={VectorPayloadField.SOURCE_ID: payload.source_id},
            timestamp_field=VectorPayloadField.UPDATED_AT,
            before=run_started,
        )
        # Per record, so debug level: the embedding job logs progress per batch at info.
        logger.debug("ingestion_complete", source_id=payload.source_id, chunks=len(chunks), collection_name=collection_name)
        return {"skipped": 0}

    async def _embed_slice(
            self,
            profile: VectorCollectionSettings,
            source_id: str,
            chunks: list[str],
            first_index: int,
            base_payload: dict,
    ) -> list[VectorPoint]:
        """Embed one slice of a record's chunks with every vector type and build its points."""
        vectors = profile.vectors
        dense = await self.embedding.embed_documents(chunks, profile=vectors.dense.embedding) if vectors.dense else None
        sparse = await self.sparse.vectorize_documents(chunks, profile=vectors.sparse.vectorizer) if vectors.sparse else None
        multi = (
            await self.embedding.embed_documents(chunks, profile=vectors.multi_vector.embedding)
            if vectors.multi_vector else None
        )
        return [
            VectorPoint(
                id=compute_uuid(f"{profile.key}:{source_id}:{first_index + offset}:{chunk}"),
                dense_vector=dense[offset] if dense is not None else None,
                multi_vector=multi[offset] if multi is not None else None,
                sparse_vector=sparse[offset] if sparse is not None else None,
                payload={**base_payload, "text": chunk},
            )
            for offset, chunk in enumerate(chunks)
        ]

    def _render_template(self, templates: list[str], payload: KnowledgeVectorPayload) -> str:
        values = payload.model_dump(mode="python")
        lines = []
        for template in templates:
            # Each YAML list entry represents a complete optional field/line.
            # Missing data omits the line, including its label.
            fields = [name for _, name, _, _ in Formatter().parse(template) if name]
            if any(not values.get(field) for field in fields):
                continue
            lines.append(template.format_map(values))
        return "\n\n".join(lines)

    async def delete_profile(self, source_id: str):
        """Delete `source_id`'s points from every collection."""
        for _, profile in self.vector_collections.items():
            await self.vector_store.delete(name=profile.key, filters={VectorPayloadField.SOURCE_ID: source_id})
