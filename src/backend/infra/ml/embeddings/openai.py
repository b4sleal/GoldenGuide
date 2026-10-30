"""OpenAI embedding adapter (dense vectors), with retry on rate limits honoring the server's reset hint."""
import asyncio

import structlog
from openai import AsyncOpenAI, RateLimitError

from backend.domain.settings.embedding import OpenAIEmbeddingSettings

logger = structlog.get_logger()

MAX_RETRIES = 5


class OpenAIEmbedding:
    def __init__(self, settings: OpenAIEmbeddingSettings):
        self.model_name = settings.model_name
        self.client = AsyncOpenAI(api_key=settings.api_key.get_secret_value())
        self.dimension = settings.dimension

    async def embed_query(self, text):
        return await self._call(lambda: self._embed(text), context="embed_query")

    async def embed_documents(self, texts):
        return [await self.embed_query(t) for t in texts]

    async def _embed(self, text):
        response = await self.client.embeddings.create(
            model=self.model_name,
            dimensions=self.dimension,
            input=text,
        )
        return response.data[0].embedding

    async def _call(self, fn, context: str):
        """Run `fn`, retrying rate-limit errors (server hint or exponential backoff); other errors propagate."""
        for attempt in range(MAX_RETRIES):
            try:
                return await fn()

            except RateLimitError as e:
                retry_after = self._retry_after(e)
                if retry_after is None:
                    retry_after = 2 ** attempt

                logger.warning(
                    "openai_rate_limited",
                    context=context,
                    retry_after=retry_after,
                )

                await asyncio.sleep(retry_after + 1)

        raise RuntimeError(f"OpenAI embedding retries exhausted for {context}")

    @staticmethod
    def _retry_after(error):
        """Seconds to wait, from the rate-limit response headers (None if absent)."""
        headers = getattr(error, "headers", None)
        if not headers:
            return None

        reset = headers.get("x-ratelimit-reset-requests")
        if reset:
            return float(reset)

        retry = headers.get("retry-after")
        if retry:
            return float(retry)

        return None
