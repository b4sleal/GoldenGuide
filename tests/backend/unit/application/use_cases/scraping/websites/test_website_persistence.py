"""Crawled website pages become wlu_pages; empty pages are skipped and retried, as in the calendar."""
from contextlib import asynccontextmanager

from backend.application.use_cases.scraping.websites.scrape.job import WebsitePersistenceExecutor
from backend.application.use_cases.scraping.websites.scrape.persistence import WebsitePersistenceService
from backend.domain.entities.jobs import JobBatchParams, JobMode
from backend.domain.entities.scraping import UNVERSIONED, ScrapePageRead, ScrapeStatus
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from tests.backend.unit.application.inline_compute import InlineCompute
from tests.backend.unit.application.use_cases.scraping.websites.factories import WLU


class Recorder:
    def __init__(self, pages=()):
        self.pages = list(pages)
        self.upserted, self.updated, self.filters = [], [], []

    async def upsert_wlu_pages(self, records):
        self.upserted.extend(records)

    async def update_scrape_pages(self, page_ids, update_data):
        self.updated.append((page_ids, update_data))

    async def fetch_pages(self, page_params, filters):
        self.filters.append(filters)
        return self.pages[page_params.offset:page_params.offset + page_params.limit]


class FakeSchoolDB:
    def __init__(self, recorder):
        self.wlu_pages = self.scraping = recorder

    @asynccontextmanager
    async def start(self):
        yield self


class FakeBlobs:
    def __init__(self, blobs):
        self.blobs = blobs

    async def download_many(self, keys, max_concurrency):
        return {key: self.blobs[key] for key in keys if key in self.blobs}


def scrape_page(id_, blob_key, needs_persistence=True):
    return ScrapePageRead(
        id=id_, url=f"https://www.wlu.ca/p{id_}.html", site_name="wlu_ca", status=ScrapeStatus.SUCCESS.value,
        blob_key=blob_key, content_hash=f"hash{id_}", needs_persistence=needs_persistence,
    )


GOOD = b"<main><h1>Benefits</h1><p>Dental and health.</p></main>"
NO_MAIN = b"<body><p>Just a moment...</p></body>"
EMPTY = b"<title>Placeholder</title><main>  </main>"  # A title but no body text.


async def test_parsed_pages_are_stored_and_only_they_are_marked_persisted():
    recorder = Recorder()
    compute = InlineCompute()
    service = WebsitePersistenceService(
        FakeSchoolDB(recorder), FakeBlobs({"a": GOOD, "b": NO_MAIN, "c": EMPTY}), compute,
    )
    pages = [scrape_page(1, "a"), scrape_page(2, "b"), scrape_page(3, "c"), scrape_page(4, None), scrape_page(5, "gone")]

    summary = await service.execute(pages, WLU)

    [record] = recorder.upserted
    assert (record.site_name, record.version, record.url) == ("wlu_ca", UNVERSIONED, "https://www.wlu.ca/p1.html")
    assert record.record_type == AcademicCalendarType.PAGE
    assert (record.title, record.content_hash) == ("Benefits", "hash1")
    assert "Dental and health." in record.content

    # Skipped pages stay needs_persistence=True and are retried by the next import.
    [(ids, update)] = recorder.updated
    assert ids == [1] and update.needs_persistence is False
    assert summary == {"pages_seen": 5, "pages_with_blob": 3, "skipped_pages": 4, "wlu_pages": 1}
    # The whole batch is parsed in one call off the event loop; I/O stays on it.
    assert compute.calls == ["parse_website_batch"]


async def test_nothing_parsed_writes_nothing():
    recorder = Recorder()
    service = WebsitePersistenceService(FakeSchoolDB(recorder), FakeBlobs({"b": NO_MAIN}), InlineCompute())

    await service.execute([scrape_page(2, "b")], WLU)

    assert recorder.upserted == [] and recorder.updated == []


class SpyService:
    def __init__(self):
        self.calls = []

    async def execute(self, pages, settings):
        self.calls.append([page.id for page in pages])
        return {"pages_seen": len(pages), "pages_with_blob": len(pages), "skipped_pages": 0, "wlu_pages": len(pages)}


async def test_executor_scopes_to_the_site_and_update_parses_only_changed_pages():
    recorder = Recorder([scrape_page(1, "a"), scrape_page(2, "b", needs_persistence=False)])
    spy = SpyService()

    result = await WebsitePersistenceExecutor(FakeSchoolDB(recorder), spy, WLU, JobMode.UPDATE).execute_batch(
        JobBatchParams(batch_no=1, offset=0, batch_size=10),
    )

    [filters] = recorder.filters
    assert (filters.site_name, filters.version, filters.has_blob) == ("wlu_ca", UNVERSIONED, True)
    assert set(filters.statuses) == {ScrapeStatus.SUCCESS, ScrapeStatus.SKIPPED}
    assert spy.calls == [[1]]
    assert result.processed_count == 2
    assert result.metadata["pages_unchanged"] == 1


async def test_fresh_executor_reparses_pages_already_persisted():
    recorder = Recorder([scrape_page(1, "a"), scrape_page(2, "b", needs_persistence=False)])
    spy = SpyService()

    result = await WebsitePersistenceExecutor(FakeSchoolDB(recorder), spy, WLU, JobMode.FRESH).execute_batch(
        JobBatchParams(batch_no=1, offset=0, batch_size=10),
    )

    assert spy.calls == [[1, 2]]
    assert result.metadata["pages_unchanged"] == 0
