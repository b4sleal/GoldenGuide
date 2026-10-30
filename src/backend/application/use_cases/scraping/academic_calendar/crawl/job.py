"""Academic Calendar crawl as a one-shot job: build the year's crawl profile, then crawl."""
from __future__ import annotations

from backend.application.services.jobs.one_shot import OneShotJobRunner
from backend.application.services.simple_scraping.service import AsyncCrawlerRunner
from backend.application.use_cases.scraping.academic_calendar.crawl.audit import (
    AcademicCalendarCrawlAuditService,
)
from backend.application.use_cases.scraping.academic_calendar.profile import (
    AcademicCalendarProfile,
)
from backend.domain.entities.jobs import JobMode, JobStatus, JobWorkResult
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.shared.utils.academic_year import get_current_academic_year


class AcademicCalendarCrawlJob:
    JOB_NAME = "academic_calendar_crawl"

    def __init__(
            self,
            app_db: AppDB,
            runner: AsyncCrawlerRunner,
            profile: AcademicCalendarProfile,
            audit_service: AcademicCalendarCrawlAuditService,
    ) -> None:
        self.app_db = app_db
        self.runner = runner
        self.profile = profile
        self.audit_service = audit_service

    async def run(
            self,
            *,
            run_id: int,
            mode: JobMode = JobMode.FRESH,
            academic_year: str | None = None,
            page_limit: int | None = None,
            concurrency: int = 50,
            timeout_seconds: int = 30,
    ) -> dict:
        effective_year = academic_year or get_current_academic_year()

        async def work() -> JobWorkResult:
            # Built inside the job so a calendar-homepage/network failure is recorded on the run
            # (FAILED) instead of leaving it QUEUED.
            crawl_profile = await self.profile.build_profile(
                academic_year=academic_year,
                timeout_seconds=timeout_seconds,
            )
            result = await self.runner.run_site(
                profile=crawl_profile,
                mode=mode.value,
                page_limit=page_limit,
                concurrency=concurrency,
                timeout_seconds=timeout_seconds,
            )

            incomplete = result["pages_retryable_error"] or result["pages_permanent_error"]
            return JobWorkResult(summary=result, status=JobStatus.PARTIAL_SUCCESS if incomplete else JobStatus.SUCCESS)

        runner = OneShotJobRunner(
            app_db=self.app_db,
            job_name=f"{self.JOB_NAME}:{effective_year}",
            auditor=self.audit_service,
        )

        return await runner.execute(
            run_id=run_id,
            mode=mode,
            work=work,
            metadata={
                "academic_year": effective_year,
                "page_limit": page_limit,
                "concurrency": concurrency,
                "timeout_seconds": timeout_seconds,
                "flush_batch_size": self.runner.batch_size,
            },
        )