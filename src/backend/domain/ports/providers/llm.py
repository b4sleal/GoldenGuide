"""LLM port: streamed text generation and structured (schema-validated) generation by profile."""
from typing import AsyncIterator, Protocol

from pydantic import BaseModel

from backend.domain.entities.llm import LLMRequest
from backend.domain.settings.profiles import LLMProfile


class LLM(Protocol):
    def generate_stream(self, request: LLMRequest) -> AsyncIterator[str]:
        ...

    async def generate_structured[T: BaseModel](
            self,
            request: LLMRequest,
            response_model: type[T],
    ) -> T:
        """Raise NotImplementedError if the provider has no structured output; the orchestrator falls back."""
        ...


class LLMOrchestrator(Protocol):
    def generate_stream(self, request: LLMRequest, profile: LLMProfile) -> AsyncIterator[str]: ...

    async def generate_structured[T: BaseModel](
            self,
            request: LLMRequest,
            profile: LLMProfile,
            response_model: type[T],
    ) -> T:
        ...
