"""Source adapters explicitly classify incomplete one-shot retrieval."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.application.services.jobs.one_shot import OneShotJobRunner
from backend.application.use_cases.scraping.academic_calendar.crawl.job import (
    AcademicCalendarCrawlJob,
)
from backend.application.use_cases.scraping.websites.crawl.job import WebsiteCrawlJob
from backend.application.use_cases.scraping.wlu_registration.jobs import (
    RegistrationJobs,
)
from backend.domain.entities.jobs import JobStatus
from backend.domain.settings.scraping import Website


@pytest.mark.parametrize(
    "failure",
    ["pages_retryable_error", "pages_permanent_error", "sitemap_failures", None],
)
async def test_website_crawl_classifies_partial_results(monkeypatch, failure):
    async def execute(self, **kwargs):
        return await kwargs["work"]()

    monkeypatch.setattr(OneShotJobRunner, "execute", execute)
    result = {
        "pages_retryable_error": int(failure == "pages_retryable_error"),
        "pages_permanent_error": int(failure == "pages_permanent_error"),
    }
    profile = SimpleNamespace(
        build_profile=AsyncMock(return_value=object()),
        sitemap_failures=int(failure == "sitemap_failures"),
    )
    catalog = SimpleNamespace(
        websites={Website.WLU: SimpleNamespace(site_name="wlu")}, ignored_extensions=[]
    )
    job = WebsiteCrawlJob(
        None,
        None,
        SimpleNamespace(run_site=AsyncMock(return_value=result), batch_size=1),
        catalog,
    )
    monkeypatch.setattr(job, "profile_for", lambda site: profile)
    outcome = await job.run(run_id=1, site=Website.WLU)
    assert outcome.status == (
        JobStatus.PARTIAL_SUCCESS if failure else JobStatus.SUCCESS
    )


async def test_calendar_crawl_classifies_partial_results(monkeypatch):
    async def execute(self, **kwargs):
        return await kwargs["work"]()

    monkeypatch.setattr(OneShotJobRunner, "execute", execute)
    job = AcademicCalendarCrawlJob(
        None,
        SimpleNamespace(
            run_site=AsyncMock(
                return_value={"pages_retryable_error": 1, "pages_permanent_error": 0}
            ),
            batch_size=1,
        ),
        SimpleNamespace(build_profile=AsyncMock(return_value=object())),
        None,
    )
    assert (await job.run(run_id=1)).status == JobStatus.PARTIAL_SUCCESS


async def test_registration_detail_failures_are_partial(monkeypatch):
    async def execute(self, **kwargs):
        return await kwargs["work"]()

    monkeypatch.setattr(OneShotJobRunner, "execute", execute)
    job = RegistrationJobs(
        None,
        SimpleNamespace(
            extract_to_blob=AsyncMock(return_value={"detail_fetch_failures": 3})
        ),
        None,
    )
    assert (
        await job.export(1, "202609", 500, None)
    ).status == JobStatus.PARTIAL_SUCCESS
