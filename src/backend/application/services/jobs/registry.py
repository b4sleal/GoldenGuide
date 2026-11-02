"""Job registry: run a stored JobRequest by calling the job it names.

Each handler maps one request's parameters onto the existing job's `run` (or `export` / `import_term`)
method; the jobs themselves are unchanged. The registry is built once at startup by the composition
root and refuses to start unless every JobKey has a handler, so a new job cannot be submitted without
being runnable.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

from backend.application.use_cases.ingestion.embedding_job import EmbeddingJob
from backend.application.use_cases.scraping.academic_calendar.crawl.job import (
    AcademicCalendarCrawlJob,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.job import (
    AcademicCalendarPersistenceJob,
)
from backend.application.use_cases.scraping.websites.crawl.job import WebsiteCrawlJob
from backend.application.use_cases.scraping.websites.scrape.job import (
    WebsitePersistenceJob,
)
from backend.application.use_cases.scraping.wlu_registration.jobs import (
    RegistrationJobs,
)
from backend.domain.entities.job_requests import (
    AcademicCalendarCrawlParams,
    AcademicCalendarImportParams,
    FrozenJobParams,
    IndexingParams,
    JobKey,
    JobRequest,
    RegistrationExportParams,
    RegistrationImportParams,
    WebsiteCrawlParams,
    WebsiteImportParams,
)

# Runs one request for one run; the job records its own progress and outcome on that run.
type JobHandler = Callable[[int, JobRequest], Awaitable[object]]


def _expecting[P: FrozenJobParams](params_type: type[P], handle: Callable[[int, P], Awaitable[object]]) -> JobHandler:
    """A JobHandler for one params model; a request of another model is a wiring bug and raises."""
    async def handler(run_id: int, request: JobRequest) -> object:
        if not isinstance(request, params_type):
            raise TypeError(f"{request.key} request is not {params_type.__name__}")
        return await handle(run_id, request)
    return handler


class JobRegistry:
    def __init__(self, handlers: Mapping[JobKey, JobHandler]) -> None:
        missing = sorted(set(JobKey) - set(handlers))
        if missing:
            raise ValueError(f"Jobs without a handler: {missing}")
        self.handlers = dict(handlers)

    async def run(self, run_id: int, request: JobRequest) -> None:
        await self.handlers[request.key](run_id, request)


def build_job_handlers(
        *,
        academic_calendar_crawl_job: Callable[[], AcademicCalendarCrawlJob],
        academic_calendar_persistence_job: Callable[[], AcademicCalendarPersistenceJob],
        website_crawl_job: Callable[[], WebsiteCrawlJob],
        website_persistence_job: Callable[[], WebsitePersistenceJob],
        registration_jobs: Callable[[], RegistrationJobs],
        course_embedding_job: Callable[[], EmbeddingJob],
        course_term_embedding_job: Callable[[], EmbeddingJob],
        wlu_page_embedding_job: Callable[[], EmbeddingJob],
) -> dict[JobKey, JobHandler]:
    """One handler per JobKey, binding each request's parameters to its job's existing entry point.

    Each argument builds a new job (a DI Factory): jobs hold per-run state, so every run gets its own.
    """

    async def calendar_crawl(run_id: int, p: AcademicCalendarCrawlParams) -> object:
        return await academic_calendar_crawl_job().run(
            run_id=run_id, mode=p.mode, academic_year=p.academic_year, page_limit=p.page_limit,
            concurrency=p.concurrency, timeout_seconds=p.timeout_seconds,
        )

    async def calendar_import(run_id: int, p: AcademicCalendarImportParams) -> object:
        return await academic_calendar_persistence_job().run(
            run_id=run_id, mode=p.mode, academic_year=p.academic_year, batch_size=p.batch_size,
            max_concurrent_batches=p.max_concurrent_batches,
        )

    async def website_crawl(run_id: int, p: WebsiteCrawlParams) -> object:
        return await website_crawl_job().run(
            run_id=run_id, site=p.site, mode=p.mode, page_limit=p.page_limit,
            concurrency=p.concurrency, timeout_seconds=p.timeout_seconds,
        )

    async def website_import(run_id: int, p: WebsiteImportParams) -> object:
        return await website_persistence_job().run(
            run_id=run_id, site=p.site, mode=p.mode, batch_size=p.batch_size,
            max_concurrent_batches=p.max_concurrent_batches,
        )

    async def registration_export(run_id: int, p: RegistrationExportParams) -> object:
        return await registration_jobs().export(run_id, p.term_code, p.page_size, p.subject)

    async def registration_import(run_id: int, p: RegistrationImportParams) -> object:
        return await registration_jobs().import_term(run_id, p.term_code)

    def indexing(job: Callable[[], EmbeddingJob]) -> JobHandler:
        async def handler(run_id: int, p: IndexingParams) -> object:
            return await job().run(
                run_id=run_id, mode=p.mode, batch_size=p.batch_size, max_concurrent_batches=p.max_concurrent_batches,
            )
        return _expecting(IndexingParams, handler)

    return {
        JobKey.ACADEMIC_CALENDAR_CRAWL: _expecting(AcademicCalendarCrawlParams, calendar_crawl),
        JobKey.ACADEMIC_CALENDAR_IMPORT: _expecting(AcademicCalendarImportParams, calendar_import),
        JobKey.WEBSITE_CRAWL: _expecting(WebsiteCrawlParams, website_crawl),
        JobKey.WEBSITE_IMPORT: _expecting(WebsiteImportParams, website_import),
        JobKey.REGISTRATION_EXPORT: _expecting(RegistrationExportParams, registration_export),
        JobKey.REGISTRATION_IMPORT: _expecting(RegistrationImportParams, registration_import),
        JobKey.COURSE_INDEXING: indexing(course_embedding_job),
        JobKey.COURSE_TERM_INDEXING: indexing(course_term_embedding_job),
        JobKey.PAGE_INDEXING: indexing(wlu_page_embedding_job),
    }
