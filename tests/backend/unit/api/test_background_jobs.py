"""Job submission/status HTTP contracts and authorization, without external services."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.api.auth import get_principal
from backend.api.routes import ingestion, jobs, scraping
from backend.domain.entities.auth.principal import Principal, Role, Scope
from backend.domain.entities.jobs import JobMode, JobRunQueued, JobRunRead, JobStatus


def override(app, endpoint, parameter, value):
    route = next(r for r in app.routes if getattr(r, "endpoint", None) == endpoint)
    dependency = next(
        d.call for d in route.dependant.dependencies if d.name == parameter
    )
    app.dependency_overrides[dependency] = lambda: value


@pytest.mark.parametrize(
    "path,endpoint,job_param",
    [
        ("indexing/courses/sync", ingestion.ingest_courses, "job"),
        ("indexing/course-terms/sync", ingestion.ingest_course_terms, "job"),
        ("indexing/pages/sync", ingestion.ingest_wlu_pages, "job"),
        ("sources/academic-calendar/discover", scraping.crawl_academic_calendar, "job"),
        (
            "sources/academic-calendar/import",
            scraping.scrape_academic_calendar_content,
            "job",
        ),
        ("sources/websites/discover?site=wlu", scraping.crawl_website, "job"),
        ("sources/websites/import?site=wlu", scraping.import_website, "job"),
        (
            "sources/registration/export?term_code=202609",
            scraping.extract_registration_term,
            "jobs",
        ),
        (
            "sources/registration/import?term_code=202609",
            scraping.ingest_registration_term,
            "jobs",
        ),
    ],
)
def test_all_job_endpoints_accept_without_executing_work(
    app, path, endpoint, job_param
):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="admin", roles=frozenset({Role.ADMIN})
    )
    submission = SimpleNamespace(
        submit=AsyncMock(return_value=JobRunQueued(run_id=9, job_name="test"))
    )
    work = SimpleNamespace(
        job_name="test", run=AsyncMock(), export=AsyncMock(), import_term=AsyncMock()
    )
    override(app, endpoint, "submission", submission)
    override(app, endpoint, job_param, work)
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/admin/{path}", headers={"Origin": app.state.site_origin}
        )
    assert response.status_code == 202, response.text
    assert response.json()["status_url"] == "/api/v1/admin/jobs/9"
    work.run.assert_not_awaited()
    work.export.assert_not_awaited()
    work.import_term.assert_not_awaited()


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


def test_status_requires_jobs_read_scope(app):
    app.dependency_overrides[get_principal] = lambda: Principal(
        subject="svc", roles=frozenset(), scopes={Scope.SOURCES_COLLECT}
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/jobs/9").status_code == 403
