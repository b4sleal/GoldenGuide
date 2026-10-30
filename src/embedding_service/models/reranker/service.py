from fastapi import HTTPException

from backend.domain.ports.providers.reranker import Reranker


class LocalRerankerService:
    def __init__(self, models: dict[str, Reranker]):
        self.models = models

    def get_model(self, model_key: str):
        model = self.models.get(model_key)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model_key: {model_key}")
        return model

    async def rerank(self, model_key: str, query: str, documents: list[str]) -> list[float]:
        model = self.get_model(model_key)
        return await model.rerank(query, documents)
