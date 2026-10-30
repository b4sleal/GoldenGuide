"""Redis/Valkey transport adapter; no GoldenGuide cache repositories belong here."""
from redis.asyncio import Redis

_INCREMENT_WINDOW = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""

class RedisStore:
    def __init__(self, client: Redis):
        self._client = client

    async def get(self, key: str) -> bytes | None:
        return await self._client.get(key)

    async def put(self, key: str, value: bytes, ttl_seconds: int) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def put_if_absent(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        return bool(await self._client.set(key, value, ex=ttl_seconds, nx=True))

    async def take(self, key: str) -> bytes | None:
        return await self._client.getdel(key)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def increment_window(self, key: str, window_seconds: int) -> tuple[int, int]:
        count, ttl = await self._client.eval(_INCREMENT_WINDOW, 1, key, window_seconds)
        return int(count), int(ttl)
