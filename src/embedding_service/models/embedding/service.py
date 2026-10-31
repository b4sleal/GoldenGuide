"""Model-key dispatch for dense and multi-vector embedding requests."""

from fastapi import HTTPException

from backend.domain.ports.providers.embedding import Embedding
from goldenguide_common.contracts.vectors import EmbeddingVector


class LocalEmbeddingService:
    """Delegate embedding requests to one of the service's loaded model adapters."""

    def __init__(self, models: dict[str, Embedding]):
        """Create a dispatcher for models keyed by configured model name."""

        self.models = models

    def get_model(self, model_key: str):
        """Return a loaded model or raise ``404`` for an unknown model key."""

        model = self.models.get(model_key)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model_key: {model_key}")
        return model

    async def embed_query(self, model_key: str, text: str) -> EmbeddingVector:
        """Embed one query with the selected model."""

        model = self.get_model(model_key)
        return await model.embed_query(text)

    async def embed_documents(self, model_key: str, texts: list[str]) -> list[EmbeddingVector]:
        """Embed documents with the selected model while preserving input order."""

        model = self.get_model(model_key)
        return await model.embed_documents(texts)