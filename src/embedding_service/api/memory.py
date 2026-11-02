"""Observe Linux process RSS after document responses have been serialized."""

from pathlib import Path
from time import monotonic

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

RSS_HEADER = "X-Embedding-RSS-KiB"
DOCUMENT_PATHS = {"/embed/documents", "/sparse/documents"}
logger = structlog.get_logger()


def read_rss_kib(status_path: Path = Path("/proc/self/status")) -> int | None:
    """Read current resident memory, not peak RSS; unavailable off Linux."""
    try:
        lines = status_path.read_text(encoding="ascii").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    return None


class MemoryObservationMiddleware:
    """Sample document responses and emit an info sample at a configured interval.

    Samples include response serialization allocations, but are not peak-memory
    measurements. The interval is request-driven; idle services emit no samples.
    """

    def __init__(self, app: ASGIApp, info_interval_seconds: float) -> None:
        self.app = app
        self.info_interval_seconds = info_interval_seconds
        self.next_info_at = 0.0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach service RSS to successful document responses without changing bodies."""
        if scope["type"] != "http" or scope["path"] not in DOCUMENT_PATHS:
            await self.app(scope, receive, send)
            return

        async def observe(message: Message) -> None:
            if message["type"] == "http.response.start" and message["status"] == 200:
                rss_kib = read_rss_kib()
                if rss_kib is not None:
                    MutableHeaders(scope=message)[RSS_HEADER] = str(rss_kib)
                fields = {"path": scope["path"], "rss_kib": rss_kib}
                logger.debug("embedding.memory_sample", **fields)
                now = monotonic()
                if now >= self.next_info_at:
                    self.next_info_at = now + self.info_interval_seconds
                    logger.info("embedding.memory_sample", **fields)
            await send(message)

        await self.app(scope, receive, observe)
