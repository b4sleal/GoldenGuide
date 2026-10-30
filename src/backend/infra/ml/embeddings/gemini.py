"""Google Gemini embedding adapter (dense vectors, L2-normalized), with retry on quota errors."""
import asyncio
import random

import numpy as np
import structlog
from google import genai

from backend.domain.settings.embedding import GeminiEmbeddingSettings
from goldenguide_common.logging.trace_wrapper import traced

logger = structlog.get_logger()

DOCUMENT_BATCH_SIZE = 100
# Pause between document batches to stay under the per-minute quota during bulk embedding.
BATCH_PAUSE_SECONDS = 2
MAX_RETRIES = 5


def normalize_rows(vectors: list[list[float]]) -> list[list[float]]:
    """Each vector scaled to length 1, so dot product equals cosine similarity."""
    matrix = np.array(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)

    return (matrix / np.where(norms == 0, 1, norms)).tolist()


class GeminiEmbedding:
    def __init__(self, settings: GeminiEmbeddingSettings):
        self.client = genai.Client(api_key=settings.api_key.get_secret_value())
        self.model_name = settings.model_name
        self.dimension = settings.dimension

    async def embed_query(self, text):
        return await self._call(
            lambda: self._embed_single(text),
            context="embed_query",
        )

    @traced("embedding.embed_documents")
    async def embed_documents(self, texts):
        async def fn():
            results = []

            for i in range(0, len(texts), DOCUMENT_BATCH_SIZE):
                batch = texts[i:i + DOCUMENT_BATCH_SIZE]

                result = await self.client.aio.models.embed_content(
                    model=self.model_name,
                    contents=batch,
                    config=genai.types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=self.dimension,
                    ),
                )

                await asyncio.sleep(BATCH_PAUSE_SECONDS)

                results.extend([e.values for e in result.embeddings])

            return normalize_rows(results)

        return await self._call(fn, context="embed_documents")

    @traced("embedding.embed_single")
    async def _embed_single(self, text):
        result = await self.client.aio.models.embed_content(
            model=self.model_name,
            contents=text,
            config=genai.types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.dimension,
            ),
        )

        return normalize_rows([result.embeddings[0].values])[0]

    async def _call(self, fn, context: str):
        """Run `fn`, retrying quota/rate-limit errors with exponential backoff; other errors propagate."""
        for attempt in range(MAX_RETRIES):
            try:
                return await fn()
            except Exception as e:
                if "quota" not in str(e).lower() and "429" not in str(e):
                    raise

                sleep_time = 2 ** attempt + random.uniform(0, 1)
                logger.warning("gemini_embedding_rate_limited", context=context, attempt=attempt + 1,
                               retry_in_seconds=round(sleep_time, 1))
                await asyncio.sleep(sleep_time)

        raise RuntimeError(f"Gemini embedding retries exhausted for {context}")
