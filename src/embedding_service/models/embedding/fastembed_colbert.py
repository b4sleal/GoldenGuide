import asyncio
import structlog
from fastembed import LateInteractionTextEmbedding

from goldenguide_common.contracts.vectors import MultiVector
from goldenguide_common.contracts.embedding_models import FeColbertEmbeddingSettings

logger = structlog.get_logger()


class FastEmbedColbertEmbedding:
    def __init__(self, settings: FeColbertEmbeddingSettings):
        logger.info("loading_colbert_model", model_name=settings.model_name)
        providers = ["CUDAExecutionProvider"] if settings.device == "cuda" else ["CPUExecutionProvider"]
        self.client = LateInteractionTextEmbedding(settings.model_name, providers=providers)

    async def embed_query(self, text: str) -> MultiVector:
        vectors = await asyncio.to_thread(lambda: list(self.client.query_embed(text)))
        return vectors[0].tolist()

    async def embed_documents(self, texts: list[str]) -> list[MultiVector]:
        vectors = await asyncio.to_thread(lambda: list(self.client.embed(texts)))
        return [v.tolist() for v in vectors]