"""LLM port: streamed text generation and structured (schema-validated) generation by profile."""
from typing import AsyncIterator, Protocol

from pydantic import BaseModel

from backend.domain.settings.profiles import LLMProfile


class LLM(Protocol):
    async def generate(self, prompt: str) -> str:
        ...

    def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        ...

    async def generate_structured[T: BaseModel = BaseModel](
            self,
            prompt: str,
            response_model: type[T] = BaseModel,
    ) -> T:
        ...

class LLMOrchestrator(Protocol):
    async def generate(self, prompt: str, profile: LLMProfile): ...
    def generate_stream(self, prompt: str, profile: LLMProfile)-> AsyncIterator[str]: ...
    async def generate_structured[T: BaseModel = BaseModel](
            self,
            prompt: str,
            profile: LLMProfile,
            response_model: type[T] = BaseModel,
    ) -> T:
        ...