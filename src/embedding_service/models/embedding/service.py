from fastapi import HTTPException

from goldenguide_common.contracts.vectors import EmbeddingVector
from backend.domain.ports.providers.embedding import Embedding


class LocalEmbeddingService:
    def __init__(self, models: dict[str, Embedding]):
        self.models = models

    def get_model(self, model_key: str):
        model = self.models.get(model_key)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model_key: {model_key}")
        return model

    async def embed_query(self, model_key: str, text: str) -> EmbeddingVector:
        model = self.get_model(model_key)
        return await model.embed_query(text)

    async def embed_documents(self, model_key: str, texts: list[str]) -> list[EmbeddingVector]:
        model = self.get_model(model_key)
        return await model.embed_documents(texts)