"""Embedding adapter for the local embedding service (dense and ColBERT models served over HTTP)."""
import httpx

from goldenguide_common.contracts.vectors import EmbeddingVector
from goldenguide_common.contracts.embedding_models import LocalEmbeddingServiceSettings, LocalEmbeddingSettings


class LocalEmbedding:
    def __init__(
            self,
            settings: LocalEmbeddingSettings,
            service_settings: LocalEmbeddingServiceSettings,
    ):
        self.settings = settings
        self.base_url = f"http://{service_settings.host}:{service_settings.port}".rstrip("/")
        self.api_key = service_settings.api_key.get_secret_value()
        self.max_texts_per_request = service_settings.max_texts_per_request

        # One client per adapter, reused for every request (connection pooling).
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(service_settings.request_timeout_seconds),
            headers={"X-API-Key": self.api_key},
        )

    async def embed_query(self, text: str) -> EmbeddingVector:
        response = await self.client.post(
            f"{self.base_url}/embed/query",
            json={
                "model_key": self.settings.name,
                "text": text,
            },
        )
        response.raise_for_status()
        return response.json()["vectors"][0]

    async def embed_documents(self, texts: list[str]) -> list[EmbeddingVector]:
        """Vectors in input order, sent in groups of at most max_texts_per_request."""
        vectors: list[EmbeddingVector] = []
        for start in range(0, len(texts), self.max_texts_per_request):
            response = await self.client.post(
                f"{self.base_url}/embed/documents",
                json={
                    "model_key": self.settings.name,
                    "texts": texts[start:start + self.max_texts_per_request],
                },
            )
            response.raise_for_status()
            vectors.extend(response.json()["vectors"])
        return vectors

    async def close(self):
        await self.client.aclose()
