"""OAuth login transaction store port. consume() is single use (read and delete), so a callback cannot be replayed."""
from typing import Protocol

from backend.domain.entities.auth.storage import OAuthTransaction


class OAuthTransactionStore(Protocol):
    async def create(self, state: str, transaction: OAuthTransaction, ttl_seconds: int) -> None: ...
    async def consume(self, state: str) -> OAuthTransaction | None: ...
