"""Administrator endpoints that collect source data from WLU (Academic Calendar, LORIS, websites).

Each step is separate so it can be re-run on its own:
    discover (find calendar URLs) -> import (parse + store pages)
    websites: discover (sitemaps + links -> stored HTML) -> import (HTML -> wlu_pages)
    export (LORIS -> blob storage) -> import (blob -> Postgres)

Each call returns 202 with a run id. Poll the supplied status URL for the final outcome.
Duplicate active runs of the same job return 409.
"""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from backend.api.auth import require_scope
from backend.api.job_runs import accepted
from backend.api.schemas import (
    AcademicCrawlRequest,
    AcademicScrapeRequest,
    JobAccepted,
    RegistrationIngestRequest,
    RegistrationScrapeRequest,
    WebsiteCrawlRequest,
    WebsiteImportRequest,
)
from backend.application.services.jobs.job_submit import JobSubmissionService
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
    REGISTRATION_EXPORT_JOB_NAME,
    REGISTRATION_IMPORT_JOB_NAME,
)
from backend.core.di.container import AppContainer
from backend.domain.entities.auth.principal import Scope
from backend.domain.entities.job_requests import (
    AcademicCalendarCrawlParams,
    AcademicCalendarImportParams,
    RegistrationExportParams,
    RegistrationImportParams,
    WebsiteCrawlParams,
    WebsiteImportParams,
)
from backend.domain.entities.jobs import JobMode
from backend.shared.utils.academic_year import get_current_academic_year

router = APIRouter(dependencies=[Depends(require_scope(Scope.SOURCES_COLLECT))])


Submission = Annotated[JobSubmissionService, Depends(Provide[AppContainer.services.job_submission])]


@router.post("/academic-calendar/discover", status_code=202, response_model=JobAccepted)
@inject
async def crawl_academic_calendar(
    request: Request, body: Annotated[AcademicCrawlRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Crawl the Academic Calendar and record which pages exist (no parsing yet)."""
    # Default to the current academic year when none is given; the run records the resolved year.
    effective_year = body.academic_year or get_current_academic_year()
    queued = await submission.submit(
        job_name=f"{AcademicCalendarCrawlJob.JOB_NAME}:{effective_year}",
        mode=body.mode,
        request=AcademicCalendarCrawlParams(
            mode=body.mode, academic_year=effective_year, page_limit=body.page_limit,
            concurrency=body.concurrency, timeout_seconds=body.timeout_seconds,
        ),
    )
    return accepted(request, queued)


@router.post("/academic-calendar/import", status_code=202, response_model=JobAccepted)
@inject
async def scrape_academic_calendar_content(
    request: Request, body: Annotated[AcademicScrapeRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Parse discovered calendar pages and persist courses/programs in batches."""
    effective_year = body.academic_year or get_current_academic_year()
    queued = await submission.submit(
        job_name=f"{AcademicCalendarPersistenceJob.JOB_NAME}:{effective_year}",
        mode=body.mode,
        request=AcademicCalendarImportParams(
            mode=body.mode, academic_year=effective_year, batch_size=body.batch_size,
            max_concurrent_batches=body.max_concurrent_batches,
        ),
    )
    return accepted(request, queued)


@router.post("/websites/discover", status_code=202, response_model=JobAccepted)
@inject
async def crawl_website(
    request: Request, body: Annotated[WebsiteCrawlRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Crawl one university website (sitemaps + links) and store its pages' HTML (no parsing yet)."""
    queued = await submission.submit(
        job_name=f"{WebsiteCrawlJob.JOB_NAME}:{body.site.value}",
        mode=body.mode,
        request=WebsiteCrawlParams(
            site=body.site, mode=body.mode, page_limit=body.page_limit,
            concurrency=body.concurrency, timeout_seconds=body.timeout_seconds,
        ),
    )
    return accepted(request, queued)


@router.post("/websites/import", status_code=202, response_model=JobAccepted)
@inject
async def import_website(
    request: Request, body: Annotated[WebsiteImportRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Parse one website's crawled pages and store them as wlu_pages, in batches."""
    queued = await submission.submit(
        job_name=f"{WebsitePersistenceJob.JOB_NAME}:{body.site.value}",
        mode=body.mode,
        request=WebsiteImportParams(
            site=body.site, mode=body.mode, batch_size=body.batch_size,
            max_concurrent_batches=body.max_concurrent_batches,
        ),
    )
    return accepted(request, queued)


@router.post("/registration/export", status_code=202, response_model=JobAccepted)
@inject
async def extract_registration_term(
    request: Request, body: Annotated[RegistrationScrapeRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Download one term's LORIS offerings as a tracked background job."""
    queued = await submission.submit(
        job_name=f"{REGISTRATION_EXPORT_JOB_NAME}:{body.term_code}",
        mode=JobMode.FRESH,
        request=RegistrationExportParams(term_code=body.term_code, page_size=body.page_size, subject=body.subject),
    )
    return accepted(request, queued)


@router.post("/registration/import", status_code=202, response_model=JobAccepted)
@inject
async def ingest_registration_term(
    request: Request, body: Annotated[RegistrationIngestRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Load a saved LORIS extract into course/term tables as a tracked background job."""
    queued = await submission.submit(
        job_name=f"{REGISTRATION_IMPORT_JOB_NAME}:{body.term_code}",
        mode=JobMode.UPDATE,
        request=RegistrationImportParams(term_code=body.term_code),
    )
    return accepted(request, queued)
