"""Login session store port. get() returns None for a missing or expired session (not logged in)."""
from typing import Protocol

from backend.domain.entities.auth.storage import AuthSession


class SessionStore(Protocol):
    async def create(self, session_id: str, session: AuthSession, ttl_seconds: int) -> None: ...
    async def get(self, session_id: str) -> AuthSession | None: ...
    async def revoke(self, session_id: str) -> None: ...
