from datetime import datetime

from pydantic import BaseModel, Field

from backend.domain.entities.jobs import JobMode, JobStatus
from backend.domain.settings.scraping import Website


class ChatRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Student question or request.",
    )


class FeedbackRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Original user question.",
    )
    response: str = Field(
        ...,
        min_length=1,
        max_length=12000,
        description="Assistant response being rated.",
    )
    rating: int = Field(
        ...,
        ge=1, le=5, description="Feedback rating from 1 (poor) to 5 (excellent).",
    )
    comment: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional written feedback.",
    )


class DocumentResponse(BaseModel):
    document_id: str
    title: str
    source_type: str
    created_at: str | None = None
    active: bool



class AcademicCrawlRequest(BaseModel):
    mode: JobMode = Field(
        default=JobMode.FRESH,
        description="Run mode. fresh = crawl seed URLs, update = crawl known pages, retry = retry failed pages.",
    )
    academic_year: str | None = Field(
        default=None,
        pattern=r"^\d{4}/\d{4}$",
        description="Academic year to crawl in YYYY/YYYY format.",
    )
    page_limit: int | None = Field(
        default=None,
        ge=1,
        description="Maximum pages to crawl. Leave empty for no limit.",
    )
    concurrency: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Number of concurrent HTTP requests.",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="HTTP timeout per request in seconds.",
    )


class WebsiteCrawlRequest(BaseModel):
    site: Website = Field(description="Website to crawl, as configured in the scraping catalog.")
    mode: JobMode = Field(
        default=JobMode.FRESH,
        description="fresh = sitemaps + links, refetching every page; update = recheck known pages "
                    "(unchanged pages answer 304); retry = retry failed pages.",
    )
    page_limit: int | None = Field(
        default=None,
        ge=1,
        description="Maximum requests in this crawl, seeds included. Leave empty for no limit.",
    )
    concurrency: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Concurrent HTTP requests. Kept low: these are the university's production websites.",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="HTTP timeout per request in seconds.",
    )


class WebsiteImportRequest(BaseModel):
    site: Website = Field(description="Website whose crawled pages are imported into wlu_pages.")
    batch_size: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Rows processed per persistence batch.",
    )
    max_concurrent_batches: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum persistence batches running concurrently.",
    )
    mode: JobMode = Field(
        default=JobMode.FRESH,
        description="fresh = process all crawled pages, retry = rerun failed batches.",
    )


class AcademicScrapeRequest(BaseModel):
    batch_size: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Rows processed per persistence batch.",
    )
    max_concurrent_batches: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum persistence batches running concurrently.",
    )
    mode: JobMode = Field(
        default=JobMode.FRESH,
        description="fresh = process all successful pages, retry = rerun failed batches.",
    )
    academic_year: str | None = Field(
        default=None,
        pattern=r"^\d{4}/\d{4}$",
        description="Academic year in YYYY/YYYY format.",
    )


class RegistrationScrapeRequest(BaseModel):
    term_code: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="Academic term code (6 digits).",
    )
    page_size: int = Field(
        default=500,
        ge=1,
        le=500,
        description="Rows requested per registration page. Default: 500.",
    )
    subject: str | None = Field(
        default=None,
        min_length=1,
        max_length=8,
        description="Optional subject filter (example: CP, BU, MA).",
    )

class IngestionRequest(BaseModel):
    mode: JobMode = Field(
        default=JobMode.UPDATE,
        description="fresh = embed every record, ignoring needs_embedding; update = embed only flagged records; "
                    "retry = rerun the failed batches of the last run.",
    )
    batch_size: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Records embedded per batch.",
    )
    max_concurrent_batches: int = Field(
        default=1,
        ge=1,
        le=20,
        description="Batches embedded concurrently. Kept at 1 by default: the GPU embedding service is the bottleneck.",
    )

class RegistrationIngestRequest(BaseModel):
    term_code: str = Field(
        ...,
        pattern=r"^\d{6}$",
        description="Academic term code to ingest from local blob storage.",
    )


class JobAccepted(BaseModel):
    """Response of an endpoint that queues a job: poll `status_url` until its status is final."""
    run_id: int
    job_name: str
    status: JobStatus
    status_url: str


class JobRunStatus(BaseModel):
    """A job run as reported by GET /admin/jobs/{run_id}."""
    run_id: int
    job_name: str
    mode: JobMode
    status: JobStatus
    finished: bool = Field(description="True once the status is final (success, partial_success, failed, cancelled).")
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    message: str | None = Field(default=None, description="Safe outcome message; internal errors stay in server records.")
