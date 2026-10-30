"""Parse a batch of stored website pages and upsert them as wlu_pages rows."""
from __future__ import annotations

import structlog

from backend.application.use_cases.scraping.websites.parse import parse_website_page
from backend.domain.entities.scraping import ScrapePageRead, ScrapePageUpdate
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType, WluPageCreate, WluPageMetadata
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.scraping import WebsiteScrapeSettings

logger = structlog.get_logger()


class WebsitePersistenceService:
    """Stored HTML of crawled website pages -> wlu_pages rows (plain pages, no structured data)."""

    def __init__(self, school_db: SchoolDB, blob_storage: BlobStorage) -> None:
        self.school_db = school_db
        self.blob_storage = blob_storage

    async def execute(self, pages: list[ScrapePageRead], settings: WebsiteScrapeSettings) -> dict:
        records: list[WluPageCreate] = []
        persisted_pages: list[ScrapePageRead] = []
        pages_with_blob = 0
        skipped_pages = 0

        blob_keys = [page.blob_key for page in pages if page.blob_key]
        blob_data_map = await self.blob_storage.download_many(blob_keys, max_concurrency=50)

        for page in pages:
            raw_bytes = blob_data_map.get(page.blob_key) if page.blob_key else None
            if not raw_bytes:
                skipped_pages += 1
                continue

            pages_with_blob += 1
            parsed = parse_website_page(raw_bytes.decode("utf-8", errors="ignore"), page.url, settings)

            if parsed is None or not parsed.title.strip() or not parsed.content.strip():
                # As in the calendar: counted as skipped and left for the next import.
                logger.warning(
                    "website_empty_page_skipped",
                    site_name=settings.site_name,
                    url=page.url,
                    missing_content_root=parsed is None,
                    empty_title=parsed is not None and not parsed.title.strip(),
                    empty_content=parsed is not None and not parsed.content.strip(),
                )
                skipped_pages += 1
                continue

            persisted_pages.append(page)
            records.append(
                WluPageCreate(
                    site_name=settings.site_name,
                    version=page.version,
                    url=page.url,
                    content_hash=page.content_hash,
                    record_type=AcademicCalendarType.PAGE,
                    title=parsed.title,
                    content=parsed.content,
                    metadata_json=WluPageMetadata(external_links=parsed.links),
                )
            )

        async with self.school_db.start() as repos:
            if records:
                await repos.wlu_pages.upsert_wlu_pages(records)

            if persisted_pages:
                await repos.scraping.update_scrape_pages(
                    page_ids=[page.id for page in persisted_pages],
                    update_data=ScrapePageUpdate(needs_persistence=False),
                )

        summary = {
            "pages_seen": len(pages),
            "pages_with_blob": pages_with_blob,
            "skipped_pages": skipped_pages,
            "wlu_pages": len(records),
        }
        logger.info("website_batch_processed", site_name=settings.site_name, **summary)
        return summary
