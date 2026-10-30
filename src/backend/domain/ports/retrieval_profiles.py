"""Retrieval profile selection port (lets the router pick a profile without depending on the service)."""
from typing import Protocol

from backend.domain.settings.profiles import RetrievalProfile


class RetrievalProfileSelector(Protocol):
    """Chooses the retrieval profile (LLM, vector search, evidence budget) for a question."""

    def route_question(self, query: str) -> RetrievalProfile:
        ...
