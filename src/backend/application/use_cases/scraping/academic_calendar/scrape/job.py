"""Academic Calendar scrape as a batch job over the year's stored pages (fresh: all; else changed only)."""
from __future__ import annotations

from backend.application.use_cases.scraping.academic_calendar.profile import AcademicCalendarProfile
from backend.application.services.jobs.job_runner import BatchJobRunner
from backend.application.use_cases.scraping.academic_calendar.scrape.audit import (
    AcademicCalendarAuditService,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.persistence import (
    AcademicCalendarPersistenceService,
)
from backend.domain.entities.jobs import JobBatchParams, JobBatchResult, JobMode
from backend.domain.entities.scraping import ScrapeStatus
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.ports.repositories.school.query_types import ScrapePageParams
from backend.shared.utils.academic_year import get_current_academic_year


class AcademicCalendarPersistenceJob:
    JOB_NAME = "academic_calendar_persistence"
    SITE_NAME = AcademicCalendarProfile.SITE_NAME

    def __init__(
            self,
            app_db: AppDB,
            school_db: SchoolDB,
            persistence_service: AcademicCalendarPersistenceService,
            audit_service: AcademicCalendarAuditService,
    ) -> None:
        self.app_db = app_db
        self.school_db = school_db
        self.persistence_service = persistence_service
        self.audit_service = audit_service

    async def run(
            self,
            *,
            run_id: int,
            batch_size: int = 200,
            max_concurrent_batches: int = 3,
            mode: JobMode = JobMode.FRESH,
            academic_year: str | None = None,
    ) -> dict:
        effective_year = academic_year or get_current_academic_year()

        executor = AcademicCalendarPersistenceExecutor(
            school_db=self.school_db,
            persistence_service=self.persistence_service,
            academic_year=effective_year,
            mode=mode,
        )

        runner = BatchJobRunner(
            app_db=self.app_db,
            job_name=f"{self.JOB_NAME}:{effective_year}",
            executor=executor,
            auditor=self.audit_service,
        )

        result = await runner.execute(
            run_id=run_id,
            batch_size=batch_size,
            max_concurrent_batches=max_concurrent_batches,
            mode=mode,
            metadata={
                "academic_year": effective_year,
                "site_name": self.SITE_NAME,
            },
        )

        return result.model_dump(mode="json")


class AcademicCalendarPersistenceExecutor:
    SITE_NAME = AcademicCalendarProfile.SITE_NAME

    def __init__(
            self,
            school_db: SchoolDB,
            persistence_service: AcademicCalendarPersistenceService,
            academic_year: str,
            mode: JobMode,
    ) -> None:
        self.school_db = school_db
        self.persistence_service = persistence_service
        self.academic_year = academic_year
        self.mode = mode

    async def count_total(self) -> int:
        async with self.school_db.start() as repos:
            return await repos.scraping.count_pages(
                filters=self._page_filter(),
            )

    async def execute_batch(self, batch: JobBatchParams) -> JobBatchResult:
        async with self.school_db.start() as repos:
            pages = await repos.scraping.fetch_pages(
                page_params=ScrapePageParams(
                    limit=batch.batch_size,
                    offset=batch.offset,
                ),
                filters=self._page_filter(),
            )

        # Fresh reprocesses every page; other modes skip pages already persisted unchanged.
        dirty_pages = pages if self.mode is JobMode.FRESH else [
            page for page in pages
            if page.needs_persistence
        ]

        if dirty_pages:
            summary = await self.persistence_service.execute(
                pages=dirty_pages,
                academic_year=self.academic_year,
            )
        else:
            summary = {
                "pages_seen": 0,
                "pages_with_blob": 0,
                "skipped_pages": 0,
                "course_payloads": 0,
                "academic_records": 0,
            }

        return JobBatchResult(
            processed_count=len(pages),
            metadata={
                "academic_year": self.academic_year,
                "site_name": self.SITE_NAME,
                "pages_fetched": len(pages),
                "pages_unchanged": len(pages) - len(dirty_pages),
                **summary,
            },
        )

    def _page_filter(self) -> ScrapePageFilter:
        """Fetched calendar pages of this academic year that have stored HTML."""
        return ScrapePageFilter(
            site_name=self.SITE_NAME,
            statuses=[
                ScrapeStatus.SUCCESS,
                ScrapeStatus.SKIPPED,
            ],
            has_blob=True,
            version=self.academic_year,
        )