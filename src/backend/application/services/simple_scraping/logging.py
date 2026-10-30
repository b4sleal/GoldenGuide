"""Crawl counters and the structured progress logs built from them (start, milestones, heartbeat, finish)."""
import asyncio
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass(slots=True)
class CrawlStats:
    """Mutable counters shared by the crawler's workers (one event loop, so no locking is needed)."""
    pages_seen: int = 0
    pages_ingestable: int = 0
    pages_empty: int = 0
    pages_skipped_ingest: int = 0
    pages_retryable_error: int = 0
    pages_permanent_error: int = 0
    # records_*: not incremented by the crawler (parsing happens in the scrape jobs); kept for log shape.
    records_page: int = 0
    records_contact: int = 0
    duplicate_links_skipped: int = 0
    duplicate_seed_urls_skipped: int = 0
    urls_enqueued: int = 0          # Every request the crawl makes counts against page_limit.
    urls_disallowed: int = 0        # Seeds/cached URLs rejected by the profile rules or robots.txt.
    redirects_blocked: int = 0      # Redirects whose target the profile rules or robots.txt reject.
    frontier_pending: int = 0
    downloader_active: int = 0


class CrawlProgressLogger:
    """Logs a crawl's counters at start, every `heartbeat_seconds` while running, and at the finish."""

    def __init__(
            self,
            site_name: str,
            stats: CrawlStats,
            queue: asyncio.Queue,
            batch_size: int,
            progress_every: int = 100,
            heartbeat_seconds: int = 5,
    ):
        self.site_name = site_name
        self.stats = stats
        self.queue = queue
        self.batch_size = batch_size
        self.progress_every = progress_every
        self.heartbeat_seconds = heartbeat_seconds
        self.next_progress_at = progress_every
        self.heartbeat_task: asyncio.Task | None = None

    def _snapshot(self, reason: str) -> None:
        self.stats.frontier_pending = self.queue.qsize()

        logger.info(
            "crawl_progress",
            site=self.site_name,
            reason=reason,
            batch_size=self.batch_size,
            pages_seen=self.stats.pages_seen,
            pages_ingestable=self.stats.pages_ingestable,
            pages_empty=self.stats.pages_empty,
            pages_skipped_ingest=self.stats.pages_skipped_ingest,
            pages_retryable_error=self.stats.pages_retryable_error,
            pages_permanent_error=self.stats.pages_permanent_error,
            records_page=self.stats.records_page,
            records_contact=self.stats.records_contact,
            duplicate_links_skipped=self.stats.duplicate_links_skipped,
            duplicate_seed_urls_skipped=self.stats.duplicate_seed_urls_skipped,
            downloader_active=self.stats.downloader_active,
            frontier_pending=self.stats.frontier_pending,
        )

    def log_started(self, seed_urls: int, concurrency: int, timeout_seconds: int) -> None:
        logger.info(
            "crawl_started",
            site=self.site_name,
            seed_urls=seed_urls,
            concurrency=concurrency,
            timeout_seconds=timeout_seconds,
            batch_size=self.batch_size,
        )

    def log_if_needed(self) -> None:
        """Log one snapshot per `progress_every` pages seen (not called by the crawler at present)."""
        while self.stats.pages_seen >= self.next_progress_at:
            self._snapshot(f"milestone_{self.next_progress_at}")
            self.next_progress_at += self.progress_every

    async def _heartbeat_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.heartbeat_seconds)
                self._snapshot("heartbeat")
        except asyncio.CancelledError:
            return

    def start_heartbeat(self) -> None:
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        if self.heartbeat_task is None:
            return
        self.heartbeat_task.cancel()
        await asyncio.gather(self.heartbeat_task, return_exceptions=True)

    def log_finished(self, reason: str = "completed") -> None:
        self.stats.frontier_pending = self.queue.qsize()

        logger.info(
            "crawl_finished",
            site=self.site_name,
            reason=reason,
            pages_seen=self.stats.pages_seen,
            pages_ingestable=self.stats.pages_ingestable,
            pages_empty=self.stats.pages_empty,
            pages_skipped_ingest=self.stats.pages_skipped_ingest,
            pages_retryable_error=self.stats.pages_retryable_error,
            pages_permanent_error=self.stats.pages_permanent_error,
            records_page=self.stats.records_page,
            records_contact=self.stats.records_contact,
            duplicate_links_skipped=self.stats.duplicate_links_skipped,
            duplicate_seed_urls_skipped=self.stats.duplicate_seed_urls_skipped,
            downloader_active=self.stats.downloader_active,
            frontier_pending=self.stats.frontier_pending,
        )