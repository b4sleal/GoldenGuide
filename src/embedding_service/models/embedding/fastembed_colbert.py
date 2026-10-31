"""FastEmbed adapter for ColBERT-style late-interaction multi-vectors."""

import asyncio

import structlog
from fastembed import LateInteractionTextEmbedding

from goldenguide_common.contracts.embedding_models import FeColbertEmbeddingSettings
from goldenguide_common.contracts.vectors import MultiVector

logger = structlog.get_logger()


class FastEmbedColbertEmbedding:
    """Generate token-level multi-vectors for late-interaction retrieval."""

    def __init__(self, settings: FeColbertEmbeddingSettings):
        """Load the configured FastEmbed model with the selected execution provider."""

        logger.info("loading_colbert_model", model_name=settings.model_name)
        providers = ["CUDAExecutionProvider"] if settings.device == "cuda" else ["CPUExecutionProvider"]
        self.client = LateInteractionTextEmbedding(settings.model_name, providers=providers)

    async def embed_query(self, text: str) -> MultiVector:
        """Encode one query and return its multi-vector representation."""

        vectors = await asyncio.to_thread(lambda: list(self.client.query_embed(text)))
        return vectors[0].tolist()

    async def embed_documents(self, texts: list[str]) -> list[MultiVector]:
        """Encode documents and preserve one multi-vector result per input."""

        vectors = await asyncio.to_thread(lambda: list(self.client.embed(texts)))
        return [v.tolist() for v in vectors]