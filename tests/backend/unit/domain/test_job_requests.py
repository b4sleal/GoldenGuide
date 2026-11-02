"""Job requests round-trip through their stored JSON and are selected by key."""

import pytest
from pydantic import ValidationError

from backend.domain.entities.job_requests import (
    AcademicCalendarCrawlParams,
    AcademicCalendarImportParams,
    IndexingParams,
    JobKey,
    JobQueue,
    RegistrationExportParams,
    RegistrationImportParams,
    WebsiteCrawlParams,
    WebsiteImportParams,
    job_queue,
    parse_job_request,
)
from backend.domain.entities.jobs import JobMode
from backend.domain.settings.scraping import Website

REQUESTS = [
    AcademicCalendarCrawlParams(
        mode=JobMode.FRESH, academic_year="2026/2027", page_limit=None, concurrency=50, timeout_seconds=30,
    ),
    AcademicCalendarImportParams(mode=JobMode.FRESH, academic_year="2026/2027", batch_size=200, max_concurrent_batches=3),
    WebsiteCrawlParams(site=Website.WLU, mode=JobMode.UPDATE, page_limit=10, concurrency=4, timeout_seconds=30),
    WebsiteImportParams(site=Website.WLU, mode=JobMode.UPDATE, batch_size=200, max_concurrent_batches=3),
    RegistrationExportParams(term_code="202609", page_size=500, subject=None),
    RegistrationImportParams(term_code="202609"),
    *(
        IndexingParams(key=key, mode=JobMode.UPDATE, batch_size=50, max_concurrent_batches=1)
        for key in (JobKey.COURSE_INDEXING, JobKey.COURSE_TERM_INDEXING, JobKey.PAGE_INDEXING)
    ),
]


def test_every_job_key_has_a_request_model():
    assert {request.key for request in REQUESTS} == set(JobKey)


@pytest.mark.parametrize("request_", REQUESTS, ids=lambda r: r.key.value)
def test_stored_json_reads_back_as_the_same_request(request_):
    assert parse_job_request(request_.model_dump(mode="json")) == request_


def test_unknown_key_or_unexpected_field_is_rejected():
    with pytest.raises(ValidationError):
        parse_job_request({"key": "not_a_job"})
    with pytest.raises(ValidationError):
        parse_job_request({"key": JobKey.REGISTRATION_IMPORT.value, "term_code": "202609", "extra": 1})


def test_indexing_runs_on_its_own_queue_and_everything_else_on_ingestion():
    assert {key: job_queue(key) for key in JobKey} == {
        key: JobQueue.INDEXING if key.value.endswith("_indexing") else JobQueue.INGESTION for key in JobKey
    }


def test_indexing_params_accept_only_indexing_keys():
    with pytest.raises(ValidationError):
        IndexingParams(key=JobKey.WEBSITE_CRAWL, mode=JobMode.UPDATE, batch_size=1, max_concurrent_batches=1)
