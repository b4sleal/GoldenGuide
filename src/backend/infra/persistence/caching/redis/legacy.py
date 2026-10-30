"""Temporary adapter for existing generic AppCache consumers; remove after migration."""
from backend.domain.settings.providers import RedisSettings
from .connection import create_redis_client

class RedisCache:
    def __init__(self, settings: RedisSettings):
        self.client = create_redis_client(settings)

    async def get(self, key: str) -> bytes | None:
        return await self.client.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> None:
        await self.client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def clear_prefix(self, prefix: str) -> None:
        cursor = 0
        while True:
            cursor, keys = await self.client.scan(cursor=cursor, match=f"{prefix}*", count=500)
            if keys:
                await self.client.unlink(*keys)
            if cursor == 0:
                break

    async def shutdown(self) -> None:
        await self.client.aclose()
