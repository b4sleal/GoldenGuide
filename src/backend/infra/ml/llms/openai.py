"""OpenAI chat-completions LLM adapter: streamed answers.

Structured output is not implemented: a profile that uses OpenAI for routing falls through to its
next fallback model.
"""
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel

from backend.domain.entities.llm import LLMRequest, MessageRole
from backend.domain.settings.llm import OpenAILLMSettings

TEMPERATURE = 0.2


def to_messages(request: LLMRequest) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    for message in request.messages:
        # Separate literals keep each entry type-checked against the SDK's per-role message types.
        if message.role is MessageRole.USER:
            messages.append({"role": "user", "content": message.content})
        else:
            messages.append({"role": "assistant", "content": message.content})
    return messages


class OpenAILLM:
    def __init__(self, settings: OpenAILLMSettings):
        self.model_name = settings.model_name
        self.client = AsyncOpenAI(api_key=settings.api_key.get_secret_value())

    async def generate_stream(self, request: LLMRequest):
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=to_messages(request),
            temperature=TEMPERATURE,
            stream=True,
        )

        async for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            if delta and delta.content:
                yield delta.content

    async def generate_structured[T: BaseModel](self, request: LLMRequest, response_model: type[T]) -> T:
        raise NotImplementedError("OpenAI structured output is not implemented")
