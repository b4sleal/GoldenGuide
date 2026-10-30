"""Vector payload metadata: every point carries embedding_source, created_at (kept across re-embeds) and
updated_at; the backfill adds what old vectors lack without overwriting anything."""
from datetime import datetime, timezone

from backend.application.use_cases.ingestion.ingest_knowledge import KnowledgeIngestor
from backend.domain.entities.ingestion_types import VectorSource
from backend.domain.ports.providers.vector_store.vector_models import VectorPayloadField

NOW = "2026-10-27T08:00:00+00:00"


class Record:
    def __init__(self, payload):
        self.payload = payload


class FakeVectorStore:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.stale_calls = []

    async def search_by_filter(self, name, filters, limit):
        return self.existing[:limit]

    async def delete_older_than(self, name, filters, timestamp_field, before):
        self.stale_calls.append((name, filters, timestamp_field, before))
        return 3


class Profile:
    def __init__(self, name, key):
        self.name, self.key = name, key


class Catalog:
    def __init__(self, *profiles):
        self.profiles = {p.name: p for p in profiles}

    def items(self):
        return self.profiles.items()


def ingestor(store):
    return KnowledgeIngestor(Catalog(Profile("multi_sparse", "collection_a"), Profile("dense", "collection_b")), store, None, None, None)


async def test_new_record_is_created_now():
    assert await ingestor(FakeVectorStore())._created_at("collection_a", "page_1", NOW) == NOW


async def test_re_embedding_keeps_the_first_created_at():
    store = FakeVectorStore([Record({VectorPayloadField.CREATED_AT: "2026-01-01T00:00:00+00:00"})])
    assert await ingestor(store)._created_at("collection_a", "page_1", NOW) == "2026-01-01T00:00:00+00:00"


async def test_sweep_targets_only_this_source_in_the_collections_ingest_writes():
    store = FakeVectorStore()
    before = datetime(2026, 10, 27, tzinfo=timezone.utc)

    deleted = await ingestor(store).delete_stale(VectorSource.WLU_PAGES, before)

    assert deleted == 3
    assert store.stale_calls == [(
        "collection_a", {VectorPayloadField.EMBEDDING_SOURCE: "wlu_pages"}, VectorPayloadField.UPDATED_AT, before,
    )]


