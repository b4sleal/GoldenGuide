"""Turn one fetched (non-304, post-redirect) response into a scrape_pages row plus newly discovered links.

Non-200 and non-HTML responses are stored PERMANENT_ERROR without parsing. HTML is uploaded to blob
storage only when its content hash changed, and is SUCCESS when the profile scrapes that URL,
otherwise SKIPPED (crawled for links only).
"""
from collections.abc import Callable
from datetime import datetime, timezone

import httpx

from backend.application.services.simple_scraping.logging import CrawlStats
from backend.domain.entities.scraping import ScrapePageCreate, ScrapeStatus, SiteProfile, ScrapePageCacheRead
from backend.domain.ports.jobs.compute import ComputeExecutor
from backend.domain.ports.providers.blob import BlobStorage
from backend.shared.utils.hashing import sha256_hash


class CrawlResponseProcessor:
    def __init__(
            self,
            profile: SiteProfile,
            stats: CrawlStats,
            seen_urls: set[str],
            blob_storage: BlobStorage,
            is_allowed: Callable[[str], bool],
            compute: ComputeExecutor,
    ):
        self.profile = profile
        self.stats = stats
        self.seen_urls = seen_urls
        self.blob_storage = blob_storage
        self.compute = compute
        # Profile rules plus robots.txt: the single gate for every URL the crawl may request.
        self.is_allowed = is_allowed

    def _discover_links(self, links: list[str]) -> list[str]:
        """Allowed links not yet seen by the crawl, normalized; marks them seen (on the loop thread)."""
        discovered_links: list[str] = []
        local_seen_links: set[str] = set()

        for link in links:
            normalized_link = self.profile.normalize_url(link)

            if not normalized_link:
                continue

            if not self.is_allowed(normalized_link):
                continue

            if normalized_link in local_seen_links:
                self.stats.duplicate_links_skipped += 1
                continue

            local_seen_links.add(normalized_link)

            if normalized_link in self.seen_urls:
                self.stats.duplicate_links_skipped += 1
                continue

            self.seen_urls.add(normalized_link)
            discovered_links.append(normalized_link)

        return discovered_links

    async def process_response(
            self,
            response: httpx.Response,
            parent_url: str | None,
            cache_state: ScrapePageCacheRead | None,
    ) -> tuple[list[str], ScrapePageCreate]:
        """(new links to crawl, the page's row). `cache_state` is the stored row of the final URL, if any."""
        url = self.profile.normalize_url(str(response.url))
        content_type = response.headers.get("content-type", "").lower()

        # Status and type are checked before the body is decoded, so error pages and
        # documents (PDFs) are never parsed as HTML for links.
        if response.status_code != 200:
            self.stats.pages_permanent_error += 1
            return [], ScrapePageCreate(
                site_name=self.profile.name,
                version=self.profile.version,
                url=url,
                status=ScrapeStatus.PERMANENT_ERROR.value,
                http_status=response.status_code,
                content_type=content_type,
                error=f"HTTP {response.status_code}",
            )

        if "text/html" not in content_type:
            self.stats.pages_permanent_error += 1
            return [], ScrapePageCreate(
                site_name=self.profile.name,
                version=self.profile.version,
                url=url,
                status=ScrapeStatus.PERMANENT_ERROR.value,
                http_status=response.status_code,
                content_type=content_type,
                error=f"non-html content type: {content_type}",
            )

        # HTML parsing is CPU-bound: off the event loop. Shared crawl state is updated back on the loop.
        links = await self.compute.run(self.profile.extract_links, response.text, url)
        discovered_links = self._discover_links(links)

        html_bytes = response.content
        new_content_hash = sha256_hash(html_bytes.decode("utf-8", errors="ignore"))
        blob_key = self.profile.get_blob_path(url)

        # Unchanged content keeps the blob already stored under the same key.
        known_hash = cache_state.content_hash if cache_state else None
        if new_content_hash != known_hash:
            await self.blob_storage.upload(blob_key, html_bytes, "text/html")

        new_etag = response.headers.get("etag")
        new_last_modified = response.headers.get("last-modified")

        if self.profile.should_scrape_url(url):
            self.stats.pages_ingestable += 1
            status = ScrapeStatus.SUCCESS.value
        else:
            self.stats.pages_skipped_ingest += 1
            status = ScrapeStatus.SKIPPED.value

        return discovered_links, ScrapePageCreate(
            site_name=self.profile.name,
            version=self.profile.version,
            url=url,
            status=status,
            http_status=response.status_code,
            content_type=content_type,
            blob_key=blob_key,
            content_hash=new_content_hash,
            etag=new_etag,
            last_modified_header=new_last_modified,
            parent_url=parent_url,  # The page this URL was discovered on (None for seeds).
            attempted_at=datetime.now(timezone.utc),
            last_success_at=datetime.now(timezone.utc),
            retry_count=0,
            error=None
        )
