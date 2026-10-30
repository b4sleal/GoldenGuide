import asyncio

import structlog
import torch
from sentence_transformers import CrossEncoder

from goldenguide_common.contracts.embedding_models import CrossEncoderRerankerSettings

logger = structlog.get_logger()


class CrossEncoderReranker:
    """Scores (query, passage) pairs with a sentence-transformers cross-encoder, entirely on `device`."""

    def __init__(self, settings: CrossEncoderRerankerSettings):
        logger.info("loading_cross_encoder_model", model_name=settings.model_name, device=settings.device)
        self.batch_size = settings.batch_size
        self.model = CrossEncoder(
            settings.model_name,
            device=settings.device,
            max_length=settings.max_length,
            model_kwargs={"dtype": "float16"} if settings.device == "cuda" else {},
        )

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        # Raw logits, not sigmoid probabilities: the sigmoid squashes strong candidates together near 1.0,
        # while logits keep the gaps that decide whether a weaker page is still relevant.
        scores = await asyncio.to_thread(
            self.model.predict,
            [(query, document) for document in documents],
            batch_size=self.batch_size,
            activation_fn=torch.nn.Identity(),
            convert_to_numpy=True,
        )
        return scores.tolist()
