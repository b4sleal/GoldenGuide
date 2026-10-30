"""Chat rate limiting: fixed-window counter per client on the byte store."""
from backend.domain.entities.auth.storage import RateLimitDecision
from backend.domain.ports.providers.caching.key_value_store import KeyValueStore
from ..keyspace import Keyspace

class RateLimitStore:
    def __init__(self, store: KeyValueStore):
        self._store = store
        self._keys = Keyspace("limits:chat")

    async def consume(self, client_id: str, limit: int, window_seconds: int) -> RateLimitDecision:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("Limit and window must be positive")
        count, ttl = await self._store.increment_window(self._keys.record(client_id), window_seconds)
        return RateLimitDecision(allowed=count <= limit, remaining=max(limit - count, 0), retry_after_seconds=max(ttl, 0))
