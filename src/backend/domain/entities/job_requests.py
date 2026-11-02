"""Jobs as data: which job to run and with what parameters (docs/backend/architecture.md#background-jobs).

A `JobRequest` is stored on its run (`job_runs.metadata_json`) when the job is submitted, so any
process (a worker container, or the API in development) can rebuild and run it from the run alone.
Each request names its job by `key`, which selects its parameter model when it is read back.
API request schemas validate user input; these models carry the already-validated values.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from backend.domain.entities.jobs import JobMode
from backend.domain.settings.scraping import Website


class JobKey(StrEnum):
    """Every job that can be submitted; one handler each in the job registry."""
    ACADEMIC_CALENDAR_CRAWL = "academic_calendar_crawl"
    ACADEMIC_CALENDAR_IMPORT = "academic_calendar_import"
    WEBSITE_CRAWL = "website_crawl"
    WEBSITE_IMPORT = "website_import"
    REGISTRATION_EXPORT = "registration_export"
    REGISTRATION_IMPORT = "registration_import"
    COURSE_INDEXING = "course_indexing"
    COURSE_TERM_INDEXING = "course_term_indexing"
    PAGE_INDEXING = "page_indexing"


class FrozenJobParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AcademicCalendarCrawlParams(FrozenJobParams):
    key: Literal[JobKey.ACADEMIC_CALENDAR_CRAWL] = JobKey.ACADEMIC_CALENDAR_CRAWL
    mode: JobMode
    academic_year: str
    page_limit: int | None
    concurrency: int
    timeout_seconds: int


class AcademicCalendarImportParams(FrozenJobParams):
    key: Literal[JobKey.ACADEMIC_CALENDAR_IMPORT] = JobKey.ACADEMIC_CALENDAR_IMPORT
    mode: JobMode
    academic_year: str
    batch_size: int
    max_concurrent_batches: int


class WebsiteCrawlParams(FrozenJobParams):
    key: Literal[JobKey.WEBSITE_CRAWL] = JobKey.WEBSITE_CRAWL
    site: Website
    mode: JobMode
    page_limit: int | None
    concurrency: int
    timeout_seconds: int


class WebsiteImportParams(FrozenJobParams):
    key: Literal[JobKey.WEBSITE_IMPORT] = JobKey.WEBSITE_IMPORT
    site: Website
    mode: JobMode
    batch_size: int
    max_concurrent_batches: int


class RegistrationExportParams(FrozenJobParams):
    key: Literal[JobKey.REGISTRATION_EXPORT] = JobKey.REGISTRATION_EXPORT
    term_code: str
    page_size: int
    subject: str | None


class RegistrationImportParams(FrozenJobParams):
    key: Literal[JobKey.REGISTRATION_IMPORT] = JobKey.REGISTRATION_IMPORT
    term_code: str


type IndexingKey = Literal[JobKey.COURSE_INDEXING, JobKey.COURSE_TERM_INDEXING, JobKey.PAGE_INDEXING]


class IndexingParams(FrozenJobParams):
    """Embedding sync of one source; `key` says which (courses, course terms or pages)."""
    key: IndexingKey
    mode: JobMode
    batch_size: int
    max_concurrent_batches: int


type JobRequest = Annotated[
    AcademicCalendarCrawlParams
    | AcademicCalendarImportParams
    | WebsiteCrawlParams
    | WebsiteImportParams
    | RegistrationExportParams
    | RegistrationImportParams
    | IndexingParams,
    Field(discriminator="key"),
]

class JobQueue(StrEnum):
    """Worker queues. Separate queues let indexing (GPU-bound) and collection run on different workers."""
    INGESTION = "ingestion"       # Crawls, imports, LORIS export/import.
    INDEXING = "indexing"         # Embedding syncs.
    MAINTENANCE = "maintenance"   # The queue's own periodic upkeep (stalled-job cleanup); never a submitted job.


_INDEXING_KEYS = frozenset({JobKey.COURSE_INDEXING, JobKey.COURSE_TERM_INDEXING, JobKey.PAGE_INDEXING})


def job_queue(key: JobKey) -> JobQueue:
    """The queue a job is delivered on."""
    return JobQueue.INDEXING if key in _INDEXING_KEYS else JobQueue.INGESTION


_JOB_REQUEST = TypeAdapter(JobRequest)


def parse_job_request(data: Any) -> JobRequest:
    """A stored request read back into its parameter model; raises ValidationError if it is not one."""
    return _JOB_REQUEST.validate_python(data)
