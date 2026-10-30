"""Website scrape as a batch job over the site's stored pages (fresh: all; else changed only)."""
from __future__ import annotations

from backend.application.services.jobs.job_runner import BatchJobRunner
from backend.application.use_cases.scraping.websites.scrape.audit import WebsiteAuditService
from backend.application.use_cases.scraping.websites.scrape.persistence import WebsitePersistenceService
from backend.domain.entities.jobs import JobBatchParams, JobBatchResult, JobMode
from backend.domain.entities.scraping import UNVERSIONED, ScrapeStatus
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.query_types import ScrapePageParams
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.scraping import ScrapingCatalog, Website, WebsiteScrapeSettings


class WebsitePersistenceJob:
    JOB_NAME = "website_persistence"

    def __init__(
            self,
            app_db: AppDB,
            school_db: SchoolDB,
            persistence_service: WebsitePersistenceService,
            catalog: ScrapingCatalog,
    ) -> None:
        self.app_db = app_db
        self.school_db = school_db
        self.persistence_service = persistence_service
        self.catalog = catalog

    async def run(
            self,
            *,
            run_id: int,
            site: Website,
            batch_size: int = 200,
            max_concurrent_batches: int = 3,
            mode: JobMode = JobMode.FRESH,
    ) -> dict:
        settings = self.catalog.websites[site]

        runner = BatchJobRunner(
            app_db=self.app_db,
            job_name=f"{self.JOB_NAME}:{site.value}",
            executor=WebsitePersistenceExecutor(self.school_db, self.persistence_service, settings, mode),
            auditor=WebsiteAuditService(self.school_db, settings.site_name),
        )

        result = await runner.execute(
            run_id=run_id,
            batch_size=batch_size,
            max_concurrent_batches=max_concurrent_batches,
            mode=mode,
            metadata={"site": site.value, "site_name": settings.site_name},
        )

        return result.model_dump(mode="json")


class WebsitePersistenceExecutor:
    def __init__(
            self,
            school_db: SchoolDB,
            persistence_service: WebsitePersistenceService,
            settings: WebsiteScrapeSettings,
            mode: JobMode,
    ) -> None:
        self.school_db = school_db
        self.persistence_service = persistence_service
        self.settings = settings
        self.mode = mode

    async def count_total(self) -> int:
        async with self.school_db.start() as repos:
            return await repos.scraping.count_pages(filters=self._page_filter())

    async def execute_batch(self, batch: JobBatchParams) -> JobBatchResult:
        async with self.school_db.start() as repos:
            pages = await repos.scraping.fetch_pages(
                page_params=ScrapePageParams(limit=batch.batch_size, offset=batch.offset),
                filters=self._page_filter(),
            )

        # Fresh reprocesses every page; other modes skip pages already persisted unchanged.
        dirty_pages = pages if self.mode is JobMode.FRESH else [page for page in pages if page.needs_persistence]

        if dirty_pages:
            summary = await self.persistence_service.execute(pages=dirty_pages, settings=self.settings)
        else:
            summary = {"pages_seen": 0, "pages_with_blob": 0, "skipped_pages": 0, "wlu_pages": 0}

        return JobBatchResult(
            processed_count=len(pages),
            metadata={
                "site_name": self.settings.site_name,
                "pages_fetched": len(pages),
                "pages_unchanged": len(pages) - len(dirty_pages),
                **summary,
            },
        )

    def _page_filter(self) -> ScrapePageFilter:
        return ScrapePageFilter(
            site_name=self.settings.site_name,
            statuses=[ScrapeStatus.SUCCESS, ScrapeStatus.SKIPPED],
            has_blob=True,
            version=UNVERSIONED,
        )
