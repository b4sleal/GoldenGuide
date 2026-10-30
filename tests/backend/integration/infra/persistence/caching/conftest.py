"""Run against an isolated disposable Redis server; never a shared production DB."""
import pytest_asyncio
from redis.asyncio import Redis
from backend.infra.persistence.caching.redis.store import RedisStore

@pytest_asyncio.fixture
async def byte_store(infra_service_url):
    url = infra_service_url("REDIS_TEST_URL")
    client = Redis.from_url(url, decode_responses=False)
    try:
        await client.ping()
        # Tests isolate their keys using a random prefix at the transport boundary.
        class IsolatedStore:
            def __init__(self, store, prefix):
                self.store, self.prefix = store, prefix
            def key(self, key): return f"{self.prefix}:{key}"
            async def get(self, key): return await self.store.get(self.key(key))
            async def put(self, key, value, ttl_seconds): return await self.store.put(self.key(key), value, ttl_seconds)
            async def put_if_absent(self, key, value, ttl_seconds): return await self.store.put_if_absent(self.key(key), value, ttl_seconds)
            async def take(self, key): return await self.store.take(self.key(key))
            async def delete(self, key): return await self.store.delete(self.key(key))
            async def increment_window(self, key, window_seconds): return await self.store.increment_window(self.key(key), window_seconds)
        from uuid import uuid4
        prefix = f"ggtest:{uuid4().hex}"
        yield IsolatedStore(RedisStore(client), prefix)
    finally:
        await client.aclose()
