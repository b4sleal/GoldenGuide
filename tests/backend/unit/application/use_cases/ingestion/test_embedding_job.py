"""Embedding jobs: fresh embeds every record, update and retry only flagged ones, a failing record fails
its batch without stopping the rest, and website pages get a title header."""
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import yaml

from backend.application.use_cases.ingestion.course_terms import CourseTermEmbeddingSource
from backend.application.use_cases.ingestion.courses import CourseEmbeddingSource
from backend.application.use_cases.ingestion.embedding_job import EmbeddingBatchError, EmbeddingExecutor
from backend.application.use_cases.ingestion.ingest_knowledge import KnowledgeIngestor
from backend.application.use_cases.ingestion.wlu_pages import WluPageEmbeddingSource
from backend.application.use_cases.ingestion import embedding_job
from backend.domain.entities.ingestion_types import KnowledgeSourceType, VectorSource, WluPageVectorPayload
from backend.domain.entities.jobs import JobBatchParams, JobMode, JobRunResult, JobStatus
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType, WluPageRead

RETRIEVAL_TEXT = Path(__file__).parents[6] / "configs" / "catalogs" / "text_enrichment" / "retrieval_text.yml"


def page(id_, needs_embedding):
    return WluPageRead(
        id=id_, url=f"https://www.wlu.ca/p{id_}.html", version="unversioned", site_name="wlu_ca",
        record_type=AcademicCalendarType.PAGE, title=f"Page {id_}", content="text", metadata_json={},
        needs_embedding=needs_embedding,
    )


class FakeWluPages:
    def __init__(self, pages):
        self.pages = {p.id: p for p in pages}

    async def count_all_records(self, filters=None):
        return len(self.pages)

    async def fetch_records(self, page_params, filters=None, view_model=None):
        rows = sorted(self.pages.values(), key=lambda p: p.id)
        return rows[page_params.offset:page_params.offset + page_params.limit]

    async def update_wlu_pages(self, page_ids, update_data):
        for id_ in page_ids:
            self.pages[id_] = self.pages[id_].model_copy(update={"needs_embedding": update_data.needs_embedding})


class FakeSchoolDB:
    def __init__(self, pages):
        self.wlu_pages = FakeWluPages(pages)

    @asynccontextmanager
    async def start(self):
        yield self

    def flagged(self):
        return sorted(id_ for id_, p in self.wlu_pages.pages.items() if p.needs_embedding)


class SpyIngestor:
    def __init__(self, failing=()):
        self.failing = set(failing)
        self.source_ids = []

    async def ingest(self, payload):
        if payload.source_id in self.failing:
            raise TimeoutError("qdrant read timeout")
        self.source_ids.append(payload.source_id)


def pages():
    return [page(1, True), page(2, False), page(3, False), page(4, True), page(5, False)]


def executor(db, spy, mode):
    return EmbeddingExecutor(db, spy, WluPageEmbeddingSource(), mode)


async def run_all(db, spy, mode, batch_size=2):
    """Execute every batch, as BatchJobRunner would, collecting failures instead of stopping."""
    ex = executor(db, spy, mode)
    total = await ex.count_total()
    failures = []
    for batch_no, offset in enumerate(range(0, total, batch_size), start=1):
        try:
            await ex.execute_batch(JobBatchParams(batch_no=batch_no, offset=offset, batch_size=batch_size))
        except EmbeddingBatchError as exc:
            failures.append((offset, exc.source_ids))
    return failures


async def test_fresh_embeds_every_record_even_when_already_embedded():
    db, spy = FakeSchoolDB(pages()), SpyIngestor()

    assert await run_all(db, spy, JobMode.FRESH) == []
    assert spy.source_ids == [f"page_{i}" for i in range(1, 6)]
    assert db.flagged() == []


@pytest.mark.parametrize("mode", [JobMode.UPDATE, JobMode.RETRY])
async def test_update_and_retry_embed_only_flagged_records(mode):
    db, spy = FakeSchoolDB(pages()), SpyIngestor()

    await run_all(db, spy, mode)

    assert spy.source_ids == ["page_1", "page_4"]
    assert db.flagged() == []


async def test_a_failing_record_fails_its_batch_but_not_the_rest():
    db, spy = FakeSchoolDB(pages()), SpyIngestor(failing={"page_3"})

    failures = await run_all(db, spy, JobMode.FRESH)

    # Batch at offset 2 holds pages 3 and 4: 4 is still embedded, the batch reports page_3.
    assert failures == [(2, ["page_3"])]
    assert spy.source_ids == ["page_1", "page_2", "page_4", "page_5"]
    # Page 3 was not flagged before the fresh run; it is now, so retry and update find it.
    assert db.flagged() == [3]


async def test_retry_replays_the_failed_batch_and_embeds_only_what_failed():
    db = FakeSchoolDB(pages())
    await run_all(db, SpyIngestor(failing={"page_3"}), JobMode.FRESH)

    # BatchJobRunner replays the failed batch's offset; the rest of that batch is already embedded.
    spy = SpyIngestor()
    result = await executor(db, spy, JobMode.RETRY).execute_batch(JobBatchParams(batch_no=2, offset=2, batch_size=2))

    assert spy.source_ids == ["page_3"]
    assert result.metadata["records_embedded"] == 1
    assert db.flagged() == []


class CapturingRepo:
    def __init__(self):
        self.params = None

    async def capture(self, page_params, filters=None, view_model=None):
        self.params = page_params
        return []

    fetch_records = fetch_courses = fetch_course_terms = capture


@pytest.mark.parametrize("source", [WluPageEmbeddingSource(), CourseEmbeddingSource(), CourseTermEmbeddingSource()])
async def test_every_source_pages_the_whole_table_by_id(source):
    """Offsets must address the same rows on retry: each source sorts by id and never filters in SQL."""
    repo = CapturingRepo()
    repos = type("Repos", (), {"wlu_pages": repo, "courses": repo, "course_terms": repo})()

    await source.fetch(repos, offset=40, limit=20)

    assert (repo.params.offset, repo.params.limit) == (40, 20)
    assert [spec.field.value for spec in repo.params.order_by] == ["id"]


def test_website_page_chunks_carry_the_page_title():
    """Website pages are stored as record_type "page"; every strategy must give them a title header."""
    strategies = yaml.safe_load(RETRIEVAL_TEXT.read_text(encoding="utf-8"))["catalog"]["text_enrichment"]["retrieval_text"]
    payload = WluPageVectorPayload(
        content="Jul 13: course selection begins", title="Important Dates and Deadlines",
        source_id="page_1", source_type=KnowledgeSourceType.WLU_PAGE, record_type=AcademicCalendarType.PAGE,
        url="https://www.wlu.ca/important-dates.html", site_name="wlu_ca", embedding_source=VectorSource.WLU_PAGES,
    )
    ingestor = KnowledgeIngestor(None, None, None, None, None)

    for name, strategy in strategies.items():
        templates = strategy[KnowledgeSourceType.WLU_PAGE.value][AcademicCalendarType.PAGE.value]
        assert "Important Dates and Deadlines" in ingestor._render_template(templates, payload), name


class SweepingIngestor:
    def __init__(self):
        self.sweeps = []

    async def delete_stale(self, source, embedded_before):
        self.sweeps.append((source, embedded_before))
        return 7


def fake_runner(status):
    class Runner:
        def __init__(self, **_):
            pass

        async def execute(self, *, run_id, batch_size, max_concurrent_batches, mode, metadata):
            return JobRunResult(
                job_name="embedding:wlu_pages", run_id=run_id, mode=mode, status=status, batch_size=batch_size,
                max_concurrent_batches=max_concurrent_batches, total_rows=0, total_batches=0, total_processed=0,
            )
    return Runner


@pytest.mark.parametrize("mode, status, swept", [
    (JobMode.FRESH, JobStatus.SUCCESS, True),
    (JobMode.FRESH, JobStatus.PARTIAL_SUCCESS, False),  # An untouched vector may be a record that failed.
    (JobMode.UPDATE, JobStatus.SUCCESS, False),         # Update skips unchanged records: untouched is not stale.
    (JobMode.RETRY, JobStatus.SUCCESS, False),
])
async def test_only_a_fully_successful_fresh_run_sweeps_stale_vectors(monkeypatch, mode, status, swept):
    monkeypatch.setattr(embedding_job, "BatchJobRunner", fake_runner(status))
    ingestor = SweepingIngestor()

    output = await embedding_job.EmbeddingJob(None, None, ingestor, WluPageEmbeddingSource()).run(
        run_id=1, mode=mode, batch_size=10, max_concurrent_batches=1,
    )

    assert bool(ingestor.sweeps) is swept
    if swept:
        [(source, _)] = ingestor.sweeps
        assert source is VectorSource.WLU_PAGES
        assert output["stale_vectors_deleted"] == 7
