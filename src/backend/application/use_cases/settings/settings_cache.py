"""Cache for the runtime settings document (JSON under one key).

The cache is optional: PostgreSQL is the source of truth. A cache that cannot be read is treated as a
miss, and a failed write is logged, so a cache outage never fails a chat request or a committed save.
"""
import json

import structlog

from backend.application.services.cache_keys import CacheKeys
from backend.domain.ports.providers.caching.cache import Cache

logger = structlog.get_logger()

DEFAULT_TTL_SECONDS = 300


class SettingsCacheService:
    """Handles the serialization and cache strategy strictly for System Settings."""

    def __init__(self, cache: Cache):
        self.cache = cache

    async def get(self) -> dict | None:
        """Cached settings, or None on a miss, an unreadable entry, or a cache outage."""
        try:
            raw = await self.cache.get(CacheKeys.settings())
            return json.loads(raw) if raw else None
        except Exception as exc:
            logger.warning("settings_cache_read_failed", error_type=type(exc).__name__, error=str(exc))
            return None

    async def set(self, settings: dict, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        try:
            await self.cache.set(
                CacheKeys.settings(),
                json.dumps(settings).encode(),
                ttl=ttl
            )
        except Exception as exc:
            # Other instances may serve the previous cached copy until it expires (at most `ttl`).
            logger.warning("settings_cache_write_failed", ttl_seconds=ttl, error_type=type(exc).__name__, error=str(exc))
