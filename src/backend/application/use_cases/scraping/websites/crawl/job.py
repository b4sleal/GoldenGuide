"""Website crawl as a one-shot job: sitemap-seeded crawl profile, then crawl."""
from __future__ import annotations

from backend.application.services.jobs.one_shot import OneShotJobRunner
from backend.application.services.simple_scraping.service import AsyncCrawlerRunner
from backend.application.use_cases.scraping.websites.crawl.audit import (
    WebsiteCrawlAuditService,
)
from backend.application.use_cases.scraping.websites.profile import WebsiteProfile
from backend.domain.entities.jobs import JobMode, JobStatus, JobWorkResult
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.scraping import ScrapingCatalog, Website


class WebsiteCrawlJob:
    JOB_NAME = "website_crawl"

    def __init__(
            self,
            app_db: AppDB,
            school_db: SchoolDB,
            runner: AsyncCrawlerRunner,
            catalog: ScrapingCatalog,
    ) -> None:
        self.app_db = app_db
        self.school_db = school_db
        self.runner = runner
        self.catalog = catalog

    def profile_for(self, site: Website) -> WebsiteProfile:
        return WebsiteProfile(self.catalog.websites[site], self.catalog.ignored_extensions)

    async def run(
            self,
            *,
            run_id: int,
            site: Website,
            mode: JobMode = JobMode.FRESH,
            page_limit: int | None = None,
            concurrency: int = 8,
            timeout_seconds: int = 30,
    ) -> dict:
        settings = self.catalog.websites[site]
        profile = self.profile_for(site)

        async def work() -> JobWorkResult:
            # Built inside the job so a sitemap/network failure is recorded on the run.
            crawl_profile = await profile.build_profile(timeout_seconds=timeout_seconds)
            result = await self.runner.run_site(
                profile=crawl_profile,
                mode=mode.value,
                page_limit=page_limit,
                concurrency=concurrency,
                timeout_seconds=timeout_seconds,
            )
            incomplete = result["pages_retryable_error"] or result["pages_permanent_error"] or profile.sitemap_failures
            return JobWorkResult(
                summary={**result, "sitemap_failures": profile.sitemap_failures},
                status=JobStatus.PARTIAL_SUCCESS if incomplete else JobStatus.SUCCESS,
            )

        runner = OneShotJobRunner(
            app_db=self.app_db,
            job_name=f"{self.JOB_NAME}:{site.value}",
            auditor=WebsiteCrawlAuditService(self.school_db, settings.site_name),
        )

        return await runner.execute(
            run_id=run_id,
            mode=mode,
            work=work,
            metadata={
                "site": site.value,
                "site_name": settings.site_name,
                "page_limit": page_limit,
                "concurrency": concurrency,
                "timeout_seconds": timeout_seconds,
                "flush_batch_size": self.runner.batch_size,
            },
        )
