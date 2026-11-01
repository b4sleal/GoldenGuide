"""Anthropic Claude LLM adapter: streamed answers.

Structured output is not implemented: a profile that uses Claude for routing falls through to its
next fallback model.
"""
import anthropic
from pydantic import BaseModel

from backend.domain.entities.llm import LLMRequest
from backend.domain.settings.llm import ClaudeLLMSettings

# Upper bound on answer length; Claude's API requires an explicit limit.
MAX_OUTPUT_TOKENS = 1024


class ClaudeLLM:
    def __init__(self, settings: ClaudeLLMSettings):
        self.model_name = settings.model_name
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.api_key.get_secret_value()
        )

    async def generate_stream(self, request: LLMRequest):
        async with self.client.messages.stream(
                model=self.model_name,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=request.system if request.system else anthropic.omit,
                messages=[{"role": message.role.value, "content": message.content} for message in request.messages],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text

    async def generate_structured[T: BaseModel](self, request: LLMRequest, response_model: type[T]) -> T:
        raise NotImplementedError("Claude structured output is not implemented")
