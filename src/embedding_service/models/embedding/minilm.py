"""Sentence-transformers adapter for ordinary dense embeddings."""

import asyncio

import structlog
from sentence_transformers import SentenceTransformer

from goldenguide_common.contracts.embedding_models import MiniLMEmbeddingSettings
from goldenguide_common.contracts.vectors import EmbeddingVector

logger = structlog.get_logger()


class MiniLMEmbedding:
    """Generate dense query and document vectors with a SentenceTransformer."""

    def __init__(self, settings: MiniLMEmbeddingSettings):
        """Load the configured model on its CPU or CUDA device."""

        logger.info("loading_minilm_model", model_name=settings.model_name, device=settings.device)
        self.model = SentenceTransformer(
            settings.model_name,
            device=settings.device,
            model_kwargs={"dtype": "float16"} if settings.device == "cuda" else {},
        )

    async def embed_query(self, text: str) -> EmbeddingVector:
        """Encode one query without blocking the asyncio event loop."""

        vector = await asyncio.to_thread(
            self.model.encode,
            text,
            convert_to_numpy=True,
        )
        return vector.tolist()

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        """Encode documents in the adapter's fixed inference batch size."""

        vectors = await asyncio.to_thread(
            self.model.encode,
            texts,
            batch_size=64,
            convert_to_numpy=True,
        )
        return vectors.tolist()