"""Crawl audit for one website: page counts by status after a crawl."""
from backend.domain.entities.scraping import ScrapePageField, ScrapeStatus
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB


class WebsiteCrawlAuditService:
    """Crawl results for one website, scoped to its site_name."""

    def __init__(self, school_db: SchoolDB, site_name: str) -> None:
        self.school_db = school_db
        self.site_name = site_name

    async def run_audit(self) -> dict:
        async with self.school_db.start() as repos:
            status_counts = await repos.scraping.count_pages_by(
                field=ScrapePageField.STATUS,
                filters=ScrapePageFilter(site_name=self.site_name),
            )
            total_success_pages = await repos.scraping.count_pages(
                filters=ScrapePageFilter(
                    site_name=self.site_name,
                    statuses=[ScrapeStatus.SUCCESS, ScrapeStatus.SKIPPED],
                    has_blob=True,
                )
            )

        return {
            "site_name": self.site_name,
            "status_counts": status_counts,
            "total_success_pages": total_success_pages,
        }
