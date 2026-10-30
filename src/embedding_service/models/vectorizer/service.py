from fastapi import HTTPException

from goldenguide_common.contracts.vectors import SparseVector
from backend.domain.ports.providers.sparse import SparseVectorizer


class LocalSparseVectorizerService:
    def __init__(self, models: dict[str, SparseVectorizer]):
        self.models = models

    def get_model(self, model_key: str):
        model = self.models.get(model_key)
        if model is None:
            raise HTTPException(status_code=404, detail=f"Unknown model_key: {model_key}")
        return model

    async def vectorize_query(self, model_key: str, text: str) -> SparseVector:
        model = self.get_model(model_key)
        return await model.vectorize_query(text)

    async def vectorize_documents(self, model_key: str, texts: list[str]) -> list[SparseVector]:
        model = self.get_model(model_key)
        return await model.vectorize_documents(texts)