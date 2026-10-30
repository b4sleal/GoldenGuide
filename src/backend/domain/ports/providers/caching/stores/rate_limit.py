"""Rate-limit counter store port (fixed windows)."""
from typing import Protocol

from backend.domain.entities.auth.storage import RateLimitDecision


class RateLimitStore(Protocol):
    async def consume(self, client_id: str, limit: int, window_seconds: int) -> RateLimitDecision: ...
