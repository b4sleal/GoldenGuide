import asyncio
import structlog
from sentence_transformers import SentenceTransformer

from goldenguide_common.contracts.vectors import EmbeddingVector
from goldenguide_common.contracts.embedding_models import MiniLMEmbeddingSettings

logger = structlog.get_logger()


class MiniLMEmbedding:
    def __init__(self, settings: MiniLMEmbeddingSettings):
        logger.info("loading_minilm_model", model_name=settings.model_name, device=settings.device)
        self.model = SentenceTransformer(
            settings.model_name,
            device=settings.device,
            model_kwargs={"dtype": "float16"} if settings.device == "cuda" else {},
        )

    async def embed_query(self, text: str) -> EmbeddingVector:
        vector = await asyncio.to_thread(
            self.model.encode,
            text,
            convert_to_numpy=True,
        )
        return vector.tolist()

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        vectors = await asyncio.to_thread(
            self.model.encode,
            texts,
            batch_size=64,
            convert_to_numpy=True,
        )
        return vectors.tolist()