"""Login session store. Expired sessions read as None even before Redis evicts them."""
from datetime import datetime, timezone

from backend.domain.entities.auth.storage import AuthSession
from backend.domain.ports.providers.caching.key_value_store import KeyValueStore
from ..codec import encode_session, decode_session
from ..keyspace import Keyspace

class SessionStore:
    def __init__(self, store: KeyValueStore):
        self._store = store
        self._keys = Keyspace("auth:session")

    async def create(self, session_id: str, session: AuthSession, ttl_seconds: int) -> None:
        if ttl_seconds <= 0 or session.expires_at <= datetime.now(timezone.utc):
            raise ValueError("Session must have a positive lifetime and future expiry")
        if not await self._store.put_if_absent(self._keys.record(session_id), encode_session(session), ttl_seconds):
            raise ValueError("Session already exists")

    async def get(self, session_id: str) -> AuthSession | None:
        raw = await self._store.get(self._keys.record(session_id))
        if raw is None:
            return None
        session = decode_session(raw)
        return session if session.expires_at > datetime.now(timezone.utc) else None

    async def revoke(self, session_id: str) -> None:
        await self._store.delete(self._keys.record(session_id))
