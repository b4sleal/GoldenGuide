"""Reusable byte-cache algorithm shared by school/application cache repositories."""
from backend.domain.ports.providers.caching.key_value_store import KeyValueStore
from .keyspace import Keyspace

class ByteCache:
    def __init__(self, store: KeyValueStore, namespace: str):
        self._store = store
        self._keys = Keyspace(namespace)

    async def get(self, identity: str) -> bytes | None:
        return await self._store.get(self._keys.record(identity))

    async def put(self, identity: str, data: bytes, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("TTL must be positive")
        await self._store.put(self._keys.record(identity), data, ttl_seconds)

    async def invalidate(self, identity: str) -> None:
        await self._store.delete(self._keys.record(identity))
