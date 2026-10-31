"""Model-key dispatch for reranking requests."""

from fastapi import HTTPException

from backend.domain.ports.providers.reranker import Reranker


class LocalRerankerService:
    """Delegate reranking to a loaded cross-encoder adapter."""

    def __init__(self, models: dict[str, Reranker]):
        """Create a dispatcher for configured reranker models."""

        self.models = models

    def get_model(self, model_key: str):
        """Return a loaded reranker or raise ``404`` for an unknown model key."""

        model = self.models.get(model_key)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model_key: {model_key}")
        return model

    async def rerank(self, model_key: str, query: str, documents: list[str]) -> list[float]:
        """Score documents with the selected model, preserving input order."""

        model = self.get_model(model_key)
        return await model.rerank(query, documents)
