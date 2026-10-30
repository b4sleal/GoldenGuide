"""Scrape audit for one website: wlu_pages counts by record type."""
from __future__ import annotations

from backend.domain.entities.scraping import ScrapeStatus
from backend.domain.ports.repositories.filters import ScrapePageFilter, WluPageFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB


class WebsiteAuditService:
    """Import results for one website, scoped to its site_name (never global totals)."""

    def __init__(self, school_db: SchoolDB, site_name: str) -> None:
        self.school_db = school_db
        self.site_name = site_name

    async def run_audit(self) -> dict:
        page_filter = WluPageFilter(site_name=self.site_name)

        async with self.school_db.start() as repos:
            total_wlu_pages = await repos.wlu_pages.count_all_records(filters=page_filter)
            record_type_counts = await repos.wlu_pages.count_by_record_type(filters=page_filter)
            total_success_pages = await repos.scraping.count_pages(
                filters=ScrapePageFilter(
                    site_name=self.site_name,
                    statuses=[ScrapeStatus.SUCCESS, ScrapeStatus.SKIPPED],
                    has_blob=True,
                )
            )

        return {
            "site_name": self.site_name,
            "total_wlu_pages": total_wlu_pages,
            "record_type_counts": record_type_counts,
            "total_success_pages": total_success_pages,
        }
