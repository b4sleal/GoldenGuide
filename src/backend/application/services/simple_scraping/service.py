"""Breadth-first async crawler for one configured site (SiteProfile): fetch pages, store HTML, record status.

Discovery only: raw HTML goes to blob storage and one scrape_pages row per URL records its outcome;
parsing into records is a separate scrape job. Every URL requested (seed, discovered link or
redirect hop) passes the same gate: the profile's rules plus robots.txt.

Modes (CrawlMode): FRESH starts from the profile's seeds, UPDATE re-checks stored pages with
conditional requests (ETag / Last-Modified, 304 keeps the stored blob), RETRY re-fetches pages that
ended in a retryable error.

Errors: a network failure for one page is stored RETRYABLE_ERROR and the crawl continues; an error in
processing or persistence aborts the crawl (TaskGroup) and propagates to the job runner, which marks
the run FAILED.
"""
import asyncio
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
import structlog

from backend.application.services.simple_scraping.logging import CrawlProgressLogger, CrawlStats
from backend.application.services.simple_scraping.response_processor import CrawlResponseProcessor
from backend.application.services.simple_scraping.robots import RobotsRules
from backend.domain.entities.scraping import CrawlMode, ScrapePageCreate, ScrapeStatus, SiteProfile, ScrapePageCacheRead
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.ports.repositories.school.query_types import ScrapePageParams

logger = structlog.get_logger()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
# robots.txt groups are selected by product token; none names ours, so the `*` group applies.
ROBOTS_PRODUCT_TOKEN = "goldenguide"
# Redirects are followed by hand so every hop passes the same rules as a link would.
MAX_REDIRECTS = 5
# Rows read per query when loading a site's stored pages.
CACHE_PAGE_SIZE = 1000
PROGRESS_LOG_EVERY_PAGES = 100
PROGRESS_HEARTBEAT_SECONDS = 5


class AsyncCrawlerRunner:
    def __init__(
            self,
            school_db: SchoolDB,
            blob_storage: BlobStorage,
            batch_size: int = 100,
            transport: httpx.AsyncBaseTransport | None = None,  # Tests inject httpx.MockTransport.
    ):
        self.school_db = school_db
        self.blob_storage = blob_storage
        self.batch_size = batch_size
        self.transport = transport

    async def _iter_cached_pages(self, filters: ScrapePageFilter):
        """Stored scrape_pages rows matching `filters`, read in pages of CACHE_PAGE_SIZE."""
        offset = 0
        page_size = CACHE_PAGE_SIZE

        while True:
            async with self.school_db.start() as repos:
                pages = await repos.scraping.fetch_pages(
                    page_params=ScrapePageParams(
                        limit=page_size,
                        offset=offset,
                    ),
                    filters=filters,
                    view_model=ScrapePageCacheRead,
                )

            for page in pages:
                yield page

            if len(pages) < page_size:
                break

            offset += len(pages)

    async def _load_initial_urls(
            self,
            profile: SiteProfile,
            mode: CrawlMode,
    ) -> list[str]:
        """The crawl's starting URLs, normalized and de-duplicated: seeds (FRESH) or stored pages (UPDATE/RETRY)."""
        if mode == CrawlMode.FRESH:
            return list(dict.fromkeys(
                normalized
                for url in profile.seed_urls
                if (normalized := profile.normalize_url(url))
            ))

        if mode == CrawlMode.RETRY:
            filters = ScrapePageFilter(
                site_name=profile.name,
                status=ScrapeStatus.RETRYABLE_ERROR,
            )
        elif mode == CrawlMode.UPDATE:
            filters = ScrapePageFilter(
                site_name=profile.name,
                statuses=[ScrapeStatus.SUCCESS, ScrapeStatus.SKIPPED],
            )
        else:
            raise ValueError(f"Unsupported crawl mode: {mode}")

        urls = set()

        async for page in self._iter_cached_pages(filters):
            normalized = profile.normalize_url(page.url)
            if normalized:
                urls.add(normalized)

        return sorted(urls)

    @staticmethod
    async def _load_robots(client: httpx.AsyncClient, profile: SiteProfile) -> dict[str, RobotsRules]:
        """robots.txt per allowed host. Unreachable (5xx / network failure) disallows that host."""
        if not profile.respect_robots_txt:
            return {}

        robots: dict[str, RobotsRules] = {}
        for host in profile.allowed_domains:
            try:
                response = await client.get(f"https://{host}/robots.txt", follow_redirects=True)
            except httpx.RequestError:
                logger.warning("robots_txt_unreachable", site_name=profile.name, host=host, exc_info=True)
                robots[host] = RobotsRules.disallowing_everything()
                continue

            robots[host] = RobotsRules.for_status(response.status_code, response.text, ROBOTS_PRODUCT_TOKEN)
            if response.status_code >= 500:
                logger.warning("robots_txt_unreachable", site_name=profile.name, host=host,
                               http_status=response.status_code)
        return robots

    @staticmethod
    def _allowed(profile: SiteProfile, robots: dict[str, RobotsRules], url: str) -> bool:
        """The single crawl gate: the profile's follow rules, then robots.txt when the profile respects it."""
        if not profile.should_follow_url(url):
            return False
        if not profile.respect_robots_txt:
            return True
        rules = robots.get(urlsplit(url).netloc.lower())
        # A host without loaded rules was never checked: fail closed.
        return rules is not None and rules.can_fetch(url)

    async def run_site(
            self,
            profile: SiteProfile,
            mode: str = CrawlMode.FRESH.value,
            page_limit: int | None = None,
            concurrency: int = 50,
            timeout_seconds: int = 30,
    ) -> dict:
        """Crawl `profile` and return the crawl summary (stored as the job's batch metadata)."""
        crawl_mode = CrawlMode(mode)

        seen_urls: set[str] = set()
        queue = asyncio.Queue()
        stats = CrawlStats()

        page_buffer: list[ScrapePageCreate] = []

        timeout = httpx.Timeout(timeout_seconds)
        limits = httpx.Limits(
            max_connections=concurrency,
            max_keepalive_connections=concurrency,
        )

        async with httpx.AsyncClient(
                timeout=timeout,
                limits=limits,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=False,
                transport=self.transport,
        ) as client:
            robots = await self._load_robots(client, profile)

            def is_allowed(url: str) -> bool:
                return self._allowed(profile, robots, url)

            def spend_request() -> bool:
                """page_limit caps every page request of the crawl: seeds, links and redirect hops."""
                if page_limit is not None and stats.urls_enqueued >= page_limit:
                    return False
                stats.urls_enqueued += 1
                return True

            def enqueue(url: str, parent_url: str | None) -> bool:
                if not spend_request():
                    return False
                queue.put_nowait((url, parent_url))
                return True

            initial_urls = await self._load_initial_urls(profile, crawl_mode)

            # Stored state of every known page, loaded once per crawl: conditional-request headers
            # (UPDATE) and content hashes that let an unchanged page skip its blob upload.
            known_state_map: dict[str, ScrapePageCacheRead] = {}

            async for page in self._iter_cached_pages(
                    ScrapePageFilter(site_name=profile.name)
            ):
                known_state_map[page.url] = page

            for normalized in initial_urls:
                if normalized in seen_urls:
                    stats.duplicate_seed_urls_skipped += 1
                    continue

                # Seeds and cached URLs pass the same rules as discovered links: robots.txt or an
                # exclusion added since the last crawl applies to UPDATE/RETRY runs too.
                if not is_allowed(normalized):
                    stats.urls_disallowed += 1
                    continue

                seen_urls.add(normalized)
                if not enqueue(normalized, None):
                    break

            stats.frontier_pending = queue.qsize()

            progress = CrawlProgressLogger(
                site_name=profile.name,
                stats=stats,
                queue=queue,
                batch_size=self.batch_size,
                progress_every=PROGRESS_LOG_EVERY_PAGES,
                heartbeat_seconds=PROGRESS_HEARTBEAT_SECONDS,
            )
            progress.log_started(
                seed_urls=len(initial_urls),
                concurrency=concurrency,
                timeout_seconds=timeout_seconds,
            )

            processor = CrawlResponseProcessor(
                profile=profile,
                stats=stats,
                seen_urls=seen_urls,
                blob_storage=self.blob_storage,
                is_allowed=is_allowed,
            )

            flush_lock = asyncio.Lock()

            async def flush_pages() -> None:
                """Persist buffered page rows in one transaction; serialized so workers never write twice."""
                async with flush_lock:
                    if not page_buffer:
                        return

                    batch = page_buffer[:]
                    # One row per URL: an INSERT ... ON CONFLICT cannot update the same row twice.
                    unique = list({(page.version, page.url): page for page in batch}.values())

                    async with self.school_db.start() as repos:
                        await repos.scraping.upsert_scrape_pages(unique)

                    # Remove only after the transaction context exits successfully.
                    # Other workers may have appended while persistence was running.
                    del page_buffer[:len(batch)]

            async def add_page_result(page_result: ScrapePageCreate) -> None:
                page_buffer.append(page_result)
                if len(page_buffer) >= self.batch_size:
                    await flush_pages()

            async def follow_redirects(response: httpx.Response) -> httpx.Response | str:
                """Follow redirects whose targets pass the crawl rules; the reason string if one does not."""
                for _ in range(MAX_REDIRECTS):
                    if not response.is_redirect:
                        return response
                    target = profile.normalize_url(urljoin(str(response.url), response.headers["location"]))
                    if not target or not is_allowed(target):
                        stats.redirects_blocked += 1
                        return f"redirect to a URL outside the crawl rules: {target or response.headers['location']}"
                    if target in seen_urls:
                        # Fetched (or queued) on its own: storing it twice would duplicate its row.
                        return f"redirects to an already crawled URL: {target}"
                    if not spend_request():
                        return f"page_limit reached while following redirects to: {target}"
                    seen_urls.add(target)
                    response = await client.get(target)
                if response.is_redirect:
                    return f"more than {MAX_REDIRECTS} redirects"
                return response

            async def worker() -> None:
                """Fetch queued URLs until cancelled: one page result per URL, new links back into the queue."""
                while True:
                    url, parent_url = await queue.get()
                    stats.downloader_active += 1

                    try:
                        cache_state = known_state_map.get(url)
                        request_headers = client.headers.copy()

                        if crawl_mode == CrawlMode.UPDATE and cache_state:
                            if cache_state.etag:
                                request_headers["If-None-Match"] = cache_state.etag
                            if cache_state.last_modified_header:
                                request_headers["If-Modified-Since"] = (
                                    cache_state.last_modified_header
                                )

                        attempted_at = datetime.now(timezone.utc)

                        try:
                            response = await follow_redirects(await client.get(url, headers=request_headers))
                        except httpx.RequestError as exc:
                            stats.pages_retryable_error += 1

                            logger.warning(
                                "page_crawl_failed",
                                url=url,
                                exc_info=True,
                            )

                            page_result = ScrapePageCreate(
                                site_name=profile.name,
                                version=profile.version,
                                url=url,
                                status=ScrapeStatus.RETRYABLE_ERROR.value,
                                error=f"{type(exc).__name__}: {exc}",
                                parent_url=parent_url,
                                attempted_at=attempted_at,
                            )
                            new_links = []
                        else:
                            stats.pages_seen += 1

                            if isinstance(response, str):
                                # Not fetched: nothing stored, and the page is never scraped.
                                stats.pages_skipped_ingest += 1
                                page_result = ScrapePageCreate(
                                    site_name=profile.name,
                                    version=profile.version,
                                    url=url,
                                    status=ScrapeStatus.SKIPPED.value,
                                    error=response,
                                    parent_url=parent_url,
                                    attempted_at=attempted_at,
                                )
                                new_links = []
                            elif response.status_code == httpx.codes.NOT_MODIFIED:
                                # Unchanged since the last crawl: keep the stored blob and hash.
                                if cache_state is None or not cache_state.blob_key:
                                    raise RuntimeError(
                                        f"Received HTTP 304 without cached content: {url}"
                                    )

                                stats.pages_skipped_ingest += 1

                                status = (
                                    ScrapeStatus.SUCCESS
                                    if profile.should_scrape_url(url)
                                    else ScrapeStatus.SKIPPED
                                )

                                page_result = ScrapePageCreate(
                                    site_name=profile.name,
                                    version=profile.version,
                                    url=url,
                                    status=status.value,
                                    http_status=httpx.codes.NOT_MODIFIED,
                                    content_type="text/html",
                                    blob_key=cache_state.blob_key,
                                    content_hash=cache_state.content_hash,
                                    etag=response.headers.get(
                                        "etag", cache_state.etag
                                    ),
                                    last_modified_header=response.headers.get(
                                        "last-modified",
                                        cache_state.last_modified_header,
                                    ),
                                    parent_url=parent_url,
                                    attempted_at=attempted_at,
                                    last_success_at=datetime.now(timezone.utc),
                                    retry_count=0,
                                    error=None,
                                )
                                new_links = []
                            else:
                                # After redirects the page is stored under its final URL, so its
                                # cached hash (blob-upload skip) must be that URL's, not the original's.
                                final_url = profile.normalize_url(str(response.url))
                                new_links, page_result = (
                                    await processor.process_response(
                                        response, parent_url, known_state_map.get(final_url)
                                    )
                                )
                                page_result = page_result.model_copy(
                                    update={"attempted_at": attempted_at}
                                )

                        # Persistence and processing errors propagate to the task group.
                        await add_page_result(page_result)

                        for link in new_links:
                            if not enqueue(link, url):
                                break

                    finally:
                        stats.downloader_active -= 1
                        queue.task_done()

            progress.start_heartbeat()

            try:
                async with asyncio.TaskGroup() as group:
                    workers = [
                        group.create_task(worker())
                        for _ in range(concurrency)
                    ]

                    # Every queued URL handled (including links found on the way): stop the workers.
                    await queue.join()

                    for task in workers:
                        task.cancel()

                await flush_pages()
                progress.log_finished(reason="completed")

                return {
                    "site_name": profile.name,
                    "mode": crawl_mode.value,
                    "seed_urls": len(initial_urls),
                    "page_limit": page_limit,
                    "concurrency": concurrency,
                    "timeout_seconds": timeout_seconds,
                    "flush_batch_size": self.batch_size,
                    "pages_seen": stats.pages_seen,
                    "pages_ingestable": stats.pages_ingestable,
                    "pages_empty": stats.pages_empty,
                    "pages_skipped_ingest": stats.pages_skipped_ingest,
                    "pages_retryable_error": stats.pages_retryable_error,
                    "pages_permanent_error": stats.pages_permanent_error,
                    "duplicate_links_skipped": stats.duplicate_links_skipped,
                    "duplicate_seed_urls_skipped": stats.duplicate_seed_urls_skipped,
                    "urls_disallowed": stats.urls_disallowed,
                    "redirects_blocked": stats.redirects_blocked,
                }

            except Exception:
                # Best effort: keep the pages already fetched, so the next crawl need not re-fetch them.
                # If persistence is what failed, this fails too; the original error is the one raised.
                try:
                    await flush_pages()
                except Exception as flush_exc:
                    logger.warning("crawl_buffer_not_persisted", site_name=profile.name, pages=len(page_buffer),
                                   error_type=type(flush_exc).__name__, error=str(flush_exc))
                # The error itself is recorded by the job runner; this keeps the crawl's progress counts.
                progress.log_finished(reason="failed")
                raise

            finally:
                await progress.stop_heartbeat()
