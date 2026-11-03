"""Vector payload metadata: every point carries embedding_source, created_at (kept across re-embeds) and
updated_at; the backfill adds what old vectors lack without overwriting anything."""
from datetime import datetime, timezone

from backend.application.use_cases.ingestion.ingest_knowledge import KnowledgeIngestor
from backend.domain.entities.ingestion_types import KnowledgeSourceType, VectorSource, WluPageVectorPayload
from backend.domain.entities.wlu.academic_level import AcademicLevel
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.ports.providers.vector_store.vector_models import VectorPayloadField

NOW = "2026-10-27T08:00:00+00:00"


class Record:
    def __init__(self, payload):
        self.payload = payload


class FakeVectorStore:
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.stale_calls = []
        self.payload_calls = []

    async def set_payload(self, name, filters, values, remove):
        self.payload_calls.append((name, filters, values, remove))

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


def page_payload(**changes) -> WluPageVectorPayload:
    return WluPageVectorPayload(**{
        "content": "Body text", "title": "Biology", "source_id": "page_7", "source_type": KnowledgeSourceType.WLU_PAGE,
        "record_type": AcademicCalendarType.DEPARTMENT, "embedding_source": VectorSource.WLU_PAGES,
        "url": "https://academic-calendar.wlu.ca/department.php?cal=3", "site_name": "academic_calendar_wlu",
        "academic_level": AcademicLevel.GRADUATE, **changes,
    })


async def test_payload_refresh_rewrites_the_records_fields_on_its_points_only():
    store = FakeVectorStore()

    await ingestor(store).refresh_payload(page_payload())

    [(name, filters, values, removed)] = store.payload_calls
    assert (name, filters) == ("collection_a", {VectorPayloadField.SOURCE_ID: "page_7"})
    assert values["academic_level"] == "graduate"
    # The chunk text and embed timestamps belong to the points, not the record: left as they are.
    assert not {"content", "text", VectorPayloadField.CREATED_AT, VectorPayloadField.UPDATED_AT} & set(values)
    assert removed == []


async def test_payload_refresh_removes_fields_that_are_now_empty():
    store = FakeVectorStore()

    await ingestor(store).refresh_payload(page_payload(academic_level=None, title=None))

    [(_, _, values, removed)] = store.payload_calls
    assert sorted(removed) == ["academic_level", "title"]
    assert "academic_level" not in values


