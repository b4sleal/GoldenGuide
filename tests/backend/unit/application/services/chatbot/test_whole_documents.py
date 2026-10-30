"""expand_to_whole_documents: whole pages replace their chunks when every found page fits the budget."""
from contextlib import asynccontextmanager

from backend.application.services.chatbot.whole_documents import expand_to_whole_documents
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType, WluPageRead
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk
from backend.domain.settings.profiles import WholeDocumentSettings

DATES = "Sep 8: Classes begin. Sep 15: Last day to add. Oct 7: Last day to drop. " * 10
GLOSSARY = "Audit: attending a course without credit."


def page(id_, content):
    return WluPageRead(
        id=id_, url=f"https://students.wlu.ca/p{id_}.html", version="unversioned", site_name="students_wlu",
        record_type=AcademicCalendarType.PAGE, title=f"Page {id_}", content=content, metadata_json={},
        needs_embedding=False,
    )


def chunk(source_id, text, score):
    return RetrievedChunk(content=text, score=score, payload={"source_id": source_id, "text": text, "title": source_id})


class FakeWluPages:
    def __init__(self, pages):
        self.pages = {p.id: p for p in pages}
        self.requested = []

    async def fetch_records(self, page_params, filters, view_model):
        self.requested.append(sorted(filters.record_ids))
        return [self.pages[i] for i in filters.record_ids if i in self.pages]


class FakeSchoolDB:
    def __init__(self, pages):
        self.wlu_pages = FakeWluPages(pages)

    @asynccontextmanager
    async def start(self):
        yield self


DB = [page(1, DATES), page(2, GLOSSARY)]
# Reranked hits: two chunks of the dates page around one glossary chunk, then a hit beyond the context.
HITS = [chunk("page_1", "Oct 7: Last day to drop", 0.9), chunk("page_2", "Audit: attending", 0.8),
        chunk("page_1", "Sep 8: Classes begin", 0.7), chunk("page_9", "beyond the context", 0.1)]


async def test_found_pages_that_fit_are_sent_whole_in_rank_order():
    db = FakeSchoolDB(DB)

    result = await expand_to_whole_documents(HITS, 3, WholeDocumentSettings(max_tokens=10_000), db)

    assert [h.content for h in result] == [DATES, GLOSSARY]           # One block per page, best page first.
    assert [h.payload["text"] for h in result] == [DATES, GLOSSARY]   # The context reads payload["text"].
    assert result[0].payload["source_id"] == "page_1"
    assert db.wlu_pages.requested == [[1, 2]]                          # page_9 is past max_chunks: not loaded.


async def test_page_load_failure_keeps_the_chunks_unchanged():
    class BrokenPages:
        async def fetch_records(self, page_params, filters, view_model):
            raise ConnectionError("database down")

    db = FakeSchoolDB(DB)
    db.wlu_pages = BrokenPages()

    assert await expand_to_whole_documents(HITS, 3, WholeDocumentSettings(max_tokens=10_000), db) == HITS


async def test_over_budget_keeps_the_chunks_unchanged():
    result = await expand_to_whole_documents(HITS, 3, WholeDocumentSettings(max_tokens=50), FakeSchoolDB(DB))

    assert result == HITS


async def test_disabled_or_unloadable_sources_keep_their_chunks():
    assert await expand_to_whole_documents(HITS, 3, None, FakeSchoolDB(DB)) == HITS

    course = [chunk("course_7", "CP220 Digital Electronics", 0.9)]
    assert await expand_to_whole_documents(course, 8, WholeDocumentSettings(max_tokens=10_000), FakeSchoolDB(DB)) == course


async def test_a_source_without_a_page_row_keeps_its_chunks_and_counts_towards_the_budget():
    hits = [chunk("page_1", "Oct 7", 0.9), chunk("course_7", "CP220 Digital Electronics", 0.8)]

    result = await expand_to_whole_documents(hits, 8, WholeDocumentSettings(max_tokens=10_000), FakeSchoolDB(DB))

    assert [h.content for h in result] == [DATES, "CP220 Digital Electronics"]


async def test_a_page_stored_twice_counts_once():
    # page_3 is the ?ref= copy of page_1: same text under another row. Alone, both copies exceed the budget.
    db = FakeSchoolDB([*DB, page(3, DATES)])
    hits = [chunk("page_1", "Oct 7", 0.9), chunk("page_3", "Sep 8", 0.8), chunk("page_2", "Audit", 0.7)]
    one_copy_fits = len(DATES) // 3 + len(GLOSSARY) // 3 + 50

    result = await expand_to_whole_documents(hits, 8, WholeDocumentSettings(max_tokens=one_copy_fits), db)

    assert [h.payload["source_id"] for h in result] == ["page_1", "page_2"]
    assert [h.content for h in result] == [DATES, GLOSSARY]


async def test_a_page_far_below_the_best_keeps_only_its_chunks():
    # The glossary chunk scores 2.0 below the best dates chunk: with a 1.0 gap it is not sent whole.
    hits = [chunk("page_1", "Oct 7", 5.0), chunk("page_2", "Audit: attending", 3.0)]
    settings = WholeDocumentSettings(max_tokens=10_000, max_score_gap=1.0)

    result = await expand_to_whole_documents(hits, 8, settings, FakeSchoolDB(DB))

    assert [h.content for h in result] == [DATES, "Audit: attending"]
