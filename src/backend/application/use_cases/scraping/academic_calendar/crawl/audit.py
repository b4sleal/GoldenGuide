"""Crawl audit for the Academic Calendar: page counts by status after a crawl."""
from backend.application.use_cases.scraping.academic_calendar.profile import AcademicCalendarProfile
from backend.domain.entities.scraping import ScrapeStatus, ScrapePageField
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB


class AcademicCalendarCrawlAuditService:
    SITE_NAME = AcademicCalendarProfile.SITE_NAME

    def __init__(self, school_db: SchoolDB) -> None:
        self.school_db = school_db

    async def run_audit(self) -> dict:
        async with self.school_db.start() as repos:
            # Uses the dynamic counter and explicit field mapping
            status_counts = await repos.scraping.count_pages_by(
                field=ScrapePageField.STATUS,
                filters=ScrapePageFilter(site_name=self.SITE_NAME)
            )

            total_success_pages = await repos.scraping.count_pages(
                filters=ScrapePageFilter(
                    site_name=self.SITE_NAME,
                    statuses=[
                        ScrapeStatus.SUCCESS,
                        ScrapeStatus.SKIPPED,
                    ],
                    has_blob=True,
                )
            )

        return {
            "site_name": self.SITE_NAME,
            "status_counts": status_counts,
            "total_success_pages": total_success_pages,
        }