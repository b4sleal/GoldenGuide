"""A record is embedded and written in slices; earlier points are removed only after every slice succeeded."""
import zlib
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.application.use_cases.ingestion.ingest_knowledge import KnowledgeIngestor
from backend.domain.entities.ingestion_types import (
    KnowledgeSourceType,
    VectorSource,
    WluPageVectorPayload,
)
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.ports.providers.vector_store.vector_models import VectorPayloadField
from backend.domain.settings.profiles import VectorCollectionSettings
from backend.shared.utils.hashing import compute_uuid
from goldenguide_common.contracts.vectors import SparseVector

COLLECTION = "collection_a"
SOURCE_ID = "page_1"


class EmbeddingFailed(Exception):
    pass


class FakeSplitter:
    def __init__(self, chunks):
        self.chunks = chunks

    def split(self, text, settings):
        return list(self.chunks)


class FakeEmbedder:
    """Records every call; the vector of a chunk is derived from its text so ordering is checkable."""

    def __init__(self, fail_on_call=None):
        self.calls = []
        self.fail_on_call = fail_on_call

    async def embed_documents(self, texts, profile):
        return self._vectors(texts, profile)

    async def vectorize_documents(self, texts, profile):
        return self._vectors(texts, profile)

    def _vectors(self, texts, profile):
        self.calls.append((profile, list(texts)))
        if self.fail_on_call == len(self.calls):
            raise EmbeddingFailed
        return [vector_for(profile, text) for text in texts]


def vector_for(profile, text):
    """A valid vector of the profile's kind whose value identifies the chunk."""
    value = float(zlib.crc32(text.encode()))
    if profile == "sparse":
        return SparseVector(indices=[int(value)], values=[1.0])
    if profile == "multi":
        return [[value, 1.0]]
    return [value, 1.0]


class FakeVectorStore:
    def __init__(self, fail_on_upsert=None):
        self.events = []
        self.fail_on_upsert = fail_on_upsert

    async def search_by_filter(self, name, filters, limit):
        return []

    async def upsert(self, name, points):
        self.events.append(("upsert", points))
        if self.fail_on_upsert == sum(event == "upsert" for event, _ in self.events):
            raise EmbeddingFailed

    async def delete_older_than(self, name, filters, timestamp_field, before):
        self.events.append(("delete_older_than", (name, filters, timestamp_field, before)))
        return 0

    async def delete(self, name, filters):
        self.events.append(("delete", filters))


def profile(slice_size):
    return SimpleNamespace(
        name="multi_sparse", key=COLLECTION, chunking=None, ingest_chunks_per_slice=slice_size,
        text_enrichment={},
        vectors=SimpleNamespace(
            dense=SimpleNamespace(embedding="dense"),
            sparse=SimpleNamespace(vectorizer="sparse"),
            multi_vector=SimpleNamespace(embedding="multi"),
        ),
    )


def page():
    return WluPageVectorPayload(
        content="ignored by the fake splitter", title="Page", source_id=SOURCE_ID,
        source_type=KnowledgeSourceType.WLU_PAGE, record_type=AcademicCalendarType.PAGE,
        url="https://www.wlu.ca/page.html", site_name="wlu_ca", embedding_source=VectorSource.WLU_PAGES,
    )


def ingestor(chunks, embedder, store):
    return KnowledgeIngestor(None, store, embedder, embedder, FakeSplitter(chunks))


def upserted(store):
    return [points for event, points in store.events if event == "upsert"]


async def test_large_record_is_written_in_ordered_slices_with_unchanged_ids_and_vectors():
    chunks = [f"chunk {i}" for i in range(150)]
    embedder, store = FakeEmbedder(), FakeVectorStore()

    await ingestor(chunks, embedder, store).ingest_profile(page(), profile(64))

    slices = upserted(store)
    assert [len(points) for points in slices] == [64, 64, 22]
    points = [point for points in slices for point in points]
    assert [point.id for point in points] == [
        compute_uuid(f"{COLLECTION}:{SOURCE_ID}:{index}:{chunk}") for index, chunk in enumerate(chunks)
    ]
    assert [point.dense_vector for point in points] == [vector_for("dense", chunk) for chunk in chunks]
    assert [point.sparse_vector for point in points] == [vector_for("sparse", chunk) for chunk in chunks]
    assert [point.multi_vector for point in points] == [vector_for("multi", chunk) for chunk in chunks]
    assert max(len(texts) for _, texts in embedder.calls) == 64


async def test_short_record_is_one_upsert():
    store = FakeVectorStore()
    await ingestor(["a", "b"], FakeEmbedder(), store).ingest_profile(page(), profile(64))
    assert [len(points) for points in upserted(store)] == [2]


async def test_earlier_points_are_removed_once_after_every_slice_and_never_by_full_delete():
    store = FakeVectorStore()
    await ingestor([f"c{i}" for i in range(130)], FakeEmbedder(), store).ingest_profile(page(), profile(64))

    assert [event for event, _ in store.events] == ["upsert", "upsert", "upsert", "delete_older_than"]
    name, filters, field, before = store.events[-1][1]
    assert (name, filters, field) == (COLLECTION, {VectorPayloadField.SOURCE_ID: SOURCE_ID}, VectorPayloadField.UPDATED_AT)
    written_at = {point.payload[VectorPayloadField.UPDATED_AT] for points in upserted(store) for point in points}
    # Every new point carries the run's timestamp, which is not older than the cutoff: none is deleted.
    assert written_at == {before.isoformat()}


@pytest.mark.parametrize(
    ("embedder", "store"),
    [
        # Call 4 is the dense embedding of the second slice.
        (FakeEmbedder(fail_on_call=4), FakeVectorStore()),
        (FakeEmbedder(), FakeVectorStore(fail_on_upsert=2)),
    ],
)
async def test_failed_slice_propagates_and_keeps_earlier_points(embedder, store):
    with pytest.raises(EmbeddingFailed):
        await ingestor([f"c{i}" for i in range(130)], embedder, store).ingest_profile(page(), profile(64))

    assert len(upserted(store)[0]) == 64
    assert all(event == "upsert" for event, _ in store.events)


def test_slice_size_must_be_positive():
    with pytest.raises(ValidationError, match="ingest_chunks_per_slice"):
        VectorCollectionSettings.model_validate({"ingest_chunks_per_slice": 0})
