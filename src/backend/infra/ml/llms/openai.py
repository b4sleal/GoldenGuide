"""OpenAI chat-completions LLM adapter: streamed answers and plain generation.

Structured output (generate_structured) is not implemented: a profile that uses OpenAI for routing
falls through to its next fallback model.
"""
from openai import AsyncOpenAI

from backend.domain.settings.llm import OpenAILLMSettings

TEMPERATURE = 0.2


class OpenAILLM:
    def __init__(self, settings: OpenAILLMSettings):
        self.model_name = settings.model_name
        self.client = AsyncOpenAI(api_key=settings.api_key.get_secret_value())

    async def generate_stream(self, prompt: str):
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta and delta.content:
                yield delta.content

    async def generate(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
        )

        return response.choices[0].message.content.strip()
