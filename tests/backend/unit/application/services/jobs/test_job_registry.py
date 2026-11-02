"""The registry covers every job and passes each request's parameters to a fresh job per run."""

from unittest.mock import AsyncMock

import pytest

from backend.application.services.jobs.registry import JobRegistry, build_job_handlers
from backend.domain.entities.job_requests import (
    IndexingParams,
    JobKey,
    RegistrationExportParams,
    WebsiteImportParams,
)
from backend.domain.entities.jobs import JobMode
from backend.domain.settings.scraping import Website

JOB_ARGS = (
    "academic_calendar_crawl_job", "academic_calendar_persistence_job", "website_crawl_job",
    "website_persistence_job", "registration_jobs", "course_embedding_job", "course_term_embedding_job",
    "wlu_page_embedding_job",
)


class FakeJob:
    def __init__(self):
        self.run = AsyncMock()
        self.export = AsyncMock()
        self.import_term = AsyncMock()


class Factory:
    """A DI Factory stand-in: builds a new job per call and keeps them for inspection."""

    def __init__(self):
        self.built: list[FakeJob] = []

    def __call__(self):
        self.built.append(FakeJob())
        return self.built[-1]


def registry():
    factories = {name: Factory() for name in JOB_ARGS}
    return JobRegistry(build_job_handlers(**factories)), factories


def test_every_job_key_has_a_handler_and_a_missing_one_fails_at_startup():
    handlers = build_job_handlers(**{name: Factory() for name in JOB_ARGS})
    assert set(handlers) == set(JobKey)
    del handlers[JobKey.PAGE_INDEXING]
    with pytest.raises(ValueError, match="page_indexing"):
        JobRegistry(handlers)


async def test_website_import_runs_its_job_with_the_request_parameters():
    reg, factories = registry()
    request = WebsiteImportParams(site=Website.WLU, mode=JobMode.UPDATE, batch_size=100, max_concurrent_batches=2)

    await reg.run(5, request)

    [job] = factories["website_persistence_job"].built
    job.run.assert_awaited_once_with(
        run_id=5, site=Website.WLU, mode=JobMode.UPDATE, batch_size=100, max_concurrent_batches=2,
    )


async def test_registration_export_uses_its_positional_entry_point():
    reg, factories = registry()

    await reg.run(5, RegistrationExportParams(term_code="202609", page_size=500, subject="CP"))

    [job] = factories["registration_jobs"].built
    job.export.assert_awaited_once_with(5, "202609", 500, "CP")


@pytest.mark.parametrize(
    ("key", "factory"),
    [
        (JobKey.COURSE_INDEXING, "course_embedding_job"),
        (JobKey.COURSE_TERM_INDEXING, "course_term_embedding_job"),
        (JobKey.PAGE_INDEXING, "wlu_page_embedding_job"),
    ],
)
async def test_each_indexing_key_runs_its_own_embedding_job(key, factory):
    reg, factories = registry()

    await reg.run(5, IndexingParams(key=key, mode=JobMode.FRESH, batch_size=50, max_concurrent_batches=1))

    assert [name for name, f in factories.items() if f.built] == [factory]


async def test_every_run_gets_a_fresh_job():
    reg, factories = registry()
    request = WebsiteImportParams(site=Website.WLU, mode=JobMode.UPDATE, batch_size=1, max_concurrent_batches=1)

    await reg.run(1, request)
    await reg.run(2, request)

    first, second = factories["website_persistence_job"].built
    assert first is not second
