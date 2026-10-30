"""OAuth login transaction store. create() refuses to overwrite; consume() reads and deletes atomically."""
from backend.domain.entities.auth.storage import OAuthTransaction
from backend.domain.ports.providers.caching.key_value_store import KeyValueStore
from ..codec import encode_oauth, decode_oauth
from ..keyspace import Keyspace

class OAuthTransactionStore:
    def __init__(self, store: KeyValueStore):
        self._store = store
        self._keys = Keyspace("auth:oauth")

    async def create(self, state: str, transaction: OAuthTransaction, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("TTL must be positive")
        if not await self._store.put_if_absent(self._keys.record(state), encode_oauth(transaction), ttl_seconds):
            raise ValueError("OAuth transaction already exists")

    async def consume(self, state: str) -> OAuthTransaction | None:
        raw = await self._store.take(self._keys.record(state))
        return decode_oauth(raw) if raw is not None else None
