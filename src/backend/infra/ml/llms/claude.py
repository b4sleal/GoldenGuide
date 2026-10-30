"""Anthropic Claude LLM adapter: streamed answers and plain generation.

Structured output (generate_structured) is not implemented: a profile that uses Claude for routing
falls through to its next fallback model.
"""
import anthropic

from backend.domain.settings.llm import ClaudeLLMSettings

# Upper bound on answer length; Claude's API requires an explicit limit.
MAX_OUTPUT_TOKENS = 1024


class ClaudeLLM:
    def __init__(self, settings: ClaudeLLMSettings):
        self.model_name = settings.model_name
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.api_key.get_secret_value()
        )

    async def generate_stream(self, prompt: str):
        async with self.client.messages.stream(
                model=self.model_name,
                max_tokens=MAX_OUTPUT_TOKENS,
                messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    yield event.delta.text

    async def generate(self, prompt: str) -> str:
        message = await self.client.messages.create(
            model=self.model_name,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )

        return message.content[0].text.strip()
