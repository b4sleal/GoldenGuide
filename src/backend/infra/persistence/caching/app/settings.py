"""Runtime settings cache: one key holding the serialized settings document."""
from backend.domain.ports.providers.caching.key_value_store import KeyValueStore
from ..keyspace import Keyspace

class SettingsCache:
    def __init__(self, store: KeyValueStore):
        self._store = store
        self._key = Keyspace("app:settings").singleton()

    async def get(self) -> bytes | None:
        return await self._store.get(self._key)

    async def put(self, data: bytes, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("TTL must be positive")
        await self._store.put(self._key, data, ttl_seconds)

    async def invalidate(self) -> None:
        await self._store.delete(self._key)
