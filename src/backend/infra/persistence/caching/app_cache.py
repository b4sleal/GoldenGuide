"""Application-facing generic cache (optional data); delegates to the configured cache adapter."""
from backend.domain.ports.providers.caching.cache import Cache

class AppCache:
    def __init__(self, cache: Cache):
        self.cache = cache

    async def get(self, key: str) -> bytes | None:
        return await self.cache.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        await self.cache.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        await self.cache.delete(key)

    async def clear_prefix(self, prefix: str) -> None:
        await self.cache.clear_prefix(prefix)

    async def shutdown(self) -> None:
        await self.cache.shutdown()