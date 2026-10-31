"""Model-key dispatch for sparse vectorization requests."""

from fastapi import HTTPException

from backend.domain.ports.providers.sparse import SparseVectorizer
from goldenguide_common.contracts.vectors import SparseVector


class LocalSparseVectorizerService:
    """Delegate sparse vectorization to a loaded provider adapter."""

    def __init__(self, models: dict[str, SparseVectorizer]):
        """Create a dispatcher for configured sparse-vectorizer models."""

        self.models = models

    def get_model(self, model_key: str):
        """Return a loaded vectorizer or raise ``404`` for an unknown model key."""

        model = self.models.get(model_key)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model_key: {model_key}")
        return model

    async def vectorize_query(self, model_key: str, text: str) -> SparseVector:
        """Vectorize one query with the selected sparse model."""

        model = self.get_model(model_key)
        return await model.vectorize_query(text)

    async def vectorize_documents(self, model_key: str, texts: list[str]) -> list[SparseVector]:
        """Vectorize documents with the selected model in input order."""

        model = self.get_model(model_key)
        return await model.vectorize_documents(texts)