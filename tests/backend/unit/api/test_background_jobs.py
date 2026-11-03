"""Job submission/status HTTP contracts and authorization, without external services."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.api.auth import get_principal
from backend.api.routes import ingestion, jobs, scraping
from backend.domain.entities.auth.principal import Principal, Role, Scope
from backend.domain.entities.job_requests import JobKey
from backend.domain.entities.jobs import JobMode, JobRunQueued, JobRunRead, JobStatus


def override(app, endpoint, parameter, value):
    route = next(r for r in app.routes if getattr(r, "endpoint", None) == endpoint)
    dependency = next(
        d.call for d in route.dependant.dependencies if d.name == parameter
    )
    app.dependency_overrides[dependency] = lambda: value


@pytest.mark.parametrize(
    "path,endpoint,key,job_name",
    [
        ("indexing/courses/sync", ingestion.ingest_courses, JobKey.COURSE_INDEXING, "embedding:courses"),
        ("indexing/course-terms/sync", ingestion.ingest_course_terms, JobKey.COURSE_TERM_INDEXING,
         "embedding:course_terms"),
        ("indexing/pages/sync", ingestion.ingest_wlu_pages, JobKey.PAGE_INDEXING, "embedding:wlu_pages"),
        ("sources/academic-calendar/discover?academic_year=2026/2027", scraping.crawl_academic_calendar,
         JobKey.ACADEMIC_CALENDAR_CRAWL, "academic_calendar_crawl:2026/2027"),
        ("sources/academic-calendar/import?academic_year=2026/2027", scraping.scrape_academic_calendar_content,
         JobKey.ACADEMIC_CALENDAR_IMPORT, "academic_calendar_persistence:2026/2027"),
        ("sources/websites/discover?site=wlu", scraping.crawl_website, JobKey.WEBSITE_CRAWL, "website_crawl:wlu"),
        ("sources/websites/import?site=wlu", scraping.import_website, JobKey.WEBSITE_IMPORT,
         "website_persistence:wlu"),
        ("sources/registration/export?term_code=202609", scraping.extract_registration_term,
         JobKey.REGISTRATION_EXPORT, "registration_export:202609"),
        ("sources/registration/import?term_code=202609", scraping.ingest_registration_term,
         JobKey.REGISTRATION_IMPORT, "registration_import:202609"),
    ],
)
def test_all_job_endpoints_submit_their_request_without_executing_work(app, path, endpoint, key, job_name):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="admin", roles=frozenset({Role.ADMIN})
    )
    submission = SimpleNamespace(
        submit=AsyncMock(return_value=JobRunQueued(run_id=9, job_name=job_name))
    )
    override(app, endpoint, "submission", submission)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/{path}", headers={"Origin": app.state.site_origin}
        )
    assert response.status_code == 202, response.text
    assert response.json()["status_url"] == "/api/v1/admin/jobs/9"
    # The endpoint only records the job as data; nothing runs inside the request.
    submitted = submission.submit.await_args.kwargs
    assert submitted["job_name"] == job_name
    assert submitted["request"].key == key


@pytest.mark.parametrize(
    "query,accepted",
    [
        ("mode=fresh&payload_only=true", True),
        ("mode=retry&payload_only=true", True),
        # update picks records by needs_embedding, which says nothing about their payload.
        ("mode=update&payload_only=true", False),
    ],
)
def test_payload_only_indexing_is_submitted_only_with_fresh_or_retry(app, query, accepted):
    app.dependency_overrides[get_principal] = lambda: Principal(subject="admin", roles=frozenset({Role.ADMIN}))
    submission = SimpleNamespace(submit=AsyncMock(return_value=JobRunQueued(run_id=9, job_name="embedding:courses")))
    override(app, ingestion.ingest_courses, "submission", submission)
    with TestClient(app) as client:
        response = client.post(f"/api/v1/admin/indexing/courses/sync?{query}", headers={"Origin": app.state.site_origin})

    if accepted:
        assert response.status_code == 202, response.text
        assert submission.submit.await_args.kwargs["request"].payload_only is True
    else:
        assert response.status_code == 422
        submission.submit.assert_not_awaited()


@pytest.mark.parametrize("state", list(JobStatus))
def test_status_reports_outcome_without_exposing_internal_metadata(app, state):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="svc", roles=frozenset(), scopes={Scope.JOBS_READ}
    )
    run = JobRunRead(
        id=9,
        job_name="test",
        mode=JobMode.UPDATE,
        status=state,
        metadata_json={"error": "sensitive SQL"},
    )

    @asynccontextmanager
    async def start():
        yield SimpleNamespace(
            jobs=SimpleNamespace(fetch_runs=AsyncMock(return_value=[run]))
        )

    override(app, jobs.get_job_run, "app_db", SimpleNamespace(start=start))
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/jobs/9")
    assert response.status_code == 200
    assert response.json()["finished"] == (
        state not in {JobStatus.QUEUED, JobStatus.RUNNING}
    )
    assert "sensitive" not in response.text and "metadata" not in response.json()


def serve_run(app, run):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="svc", roles=frozenset(), scopes={Scope.JOBS_READ}
    )

    @asynccontextmanager
    async def start():
        yield SimpleNamespace(
            jobs=SimpleNamespace(fetch_runs=AsyncMock(return_value=[run]))
        )

    override(app, jobs.get_job_run, "app_db", SimpleNamespace(start=start))


def test_status_reports_summary_and_audit_of_a_finished_run(app):
    summary = {"pages_success": 10, "pages_permanent_error": 2}
    audit = {"site_name": "wlu_ca", "total_success_pages": 10}
    serve_run(app, JobRunRead(
        id=9, job_name="website_crawl:wlu", mode=JobMode.FRESH, status=JobStatus.PARTIAL_SUCCESS,
        metadata_json={"summary": summary, "audit": audit, "metadata": {"concurrency": 4}},
    ))
    with TestClient(app) as client:
        body = client.get("/api/v1/admin/jobs/9").json()
    assert (body["summary"], body["audit"]) == (summary, audit)
    assert "finished" in body["message"] and "failed" not in body["message"]


def test_failed_run_reports_failure_without_error_details(app):
    serve_run(app, JobRunRead(
        id=9, job_name="test", mode=JobMode.FRESH, status=JobStatus.FAILED,
        metadata_json={"error": {"error_message": "sensitive SQL"}},
    ))
    with TestClient(app) as client:
        response = client.get("/api/v1/admin/jobs/9")
    body = response.json()
    assert "failed" in body["message"]
    assert (body["summary"], body["audit"]) == (None, None)
    assert "sensitive" not in response.text


@pytest.mark.parametrize("state", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.SUCCESS])
def test_unfinished_or_successful_run_has_no_message(app, state):
    serve_run(app, JobRunRead(id=9, job_name="test", mode=JobMode.FRESH, status=state))
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/jobs/9").json()["message"] is None


def test_status_requires_jobs_read_scope(app):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="svc", roles=frozenset(), scopes={Scope.SOURCES_COLLECT}
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/jobs/9").status_code == 403
