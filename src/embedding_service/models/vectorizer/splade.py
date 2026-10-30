import asyncio

import structlog
from fastembed import SparseTextEmbedding

from goldenguide_common.contracts.vectors import SparseVector
from goldenguide_common.contracts.embedding_models import SpladeSparseVectorizerSettings

logger = structlog.get_logger()

class SpladeSparseVectorizer:
    def __init__(self, settings=SpladeSparseVectorizerSettings):
        self.model_name = settings.model_name
        self.batch_size = settings.batch_size
        providers = ["CUDAExecutionProvider"]
        self.model = SparseTextEmbedding(model_name=self.model_name, providers=providers, threads=1)
        logger.info(
            "splade_provider_debug",
            device=settings.device,
            requested=providers,
            actual=self.model.model.model.get_providers(),
        )

    async def vectorize_query(self, text: str):
        embedding = await asyncio.to_thread(
            lambda: next(self.model.embed([text], batch_size=1))
        )
        return SparseVector(
            indices=embedding.indices.tolist(),
            values=embedding.values.tolist(),
        )

    async def vectorize_documents(self, texts: list[str]):
        embeddings = await asyncio.to_thread(
            lambda: list(
                self.model.embed(texts, batch_size=self.batch_size)
            )
        )

        return [
            SparseVector(
                indices=embedding.indices.tolist(),
                values=embedding.values.tolist(),
            )
            for embedding in embeddings
        ]