"""Scrape audit for the Academic Calendar: record counts and a sample of unmapped pages."""
from __future__ import annotations

from backend.application.use_cases.scraping.academic_calendar.profile import AcademicCalendarProfile
from backend.domain.entities.scraping import ScrapeStatus
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.ports.repositories.school.query_types import ScrapePageParams


class AcademicCalendarAuditService:
    SITE_NAME = AcademicCalendarProfile.SITE_NAME

    def __init__(self, school_db: SchoolDB) -> None:
        self.school_db = school_db

    async def run_audit(self) -> dict:
        async with self.school_db.start() as repos:
            total_courses = await repos.courses.count_courses()
            total_academic_records = await repos.wlu_pages.count_all_records()
            academic_record_type_counts = await repos.wlu_pages.count_by_record_type()

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

            unmapped_success_pages_count = await repos.scraping.count_pages(
                filters=ScrapePageFilter(
                    site_name=self.SITE_NAME,
                    status=ScrapeStatus.SUCCESS,
                    is_unmapped=True,
                )
            )

            # A sample (first 100) is enough to see which page layouts the parser does not map yet.
            unmapped_pages = await repos.scraping.fetch_pages(
                page_params=ScrapePageParams(limit=100, offset=0),
                filters=ScrapePageFilter(
                    site_name=self.SITE_NAME,
                    status=ScrapeStatus.SUCCESS,
                    is_unmapped=True,
                ),
            )

        return {
            "site_name": self.SITE_NAME,
            "total_courses": total_courses,
            "total_academic_records": total_academic_records,
            "academic_record_type_counts": academic_record_type_counts,
            "total_success_pages": total_success_pages,
            "unmapped_success_pages_count": unmapped_success_pages_count,
            "unmapped_success_page_urls_sample": [page.url for page in unmapped_pages],
        }