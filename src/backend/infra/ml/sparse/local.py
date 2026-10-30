"""Sparse vectorizer adapter for the local embedding service (SPLADE)."""
import httpx

from goldenguide_common.contracts.vectors import SparseVector
from goldenguide_common.contracts.embedding_models import LocalEmbeddingServiceSettings, LocalSparseVectorizerSettings


class LocalSparseVectorizer:
    def __init__(
            self,
            settings: LocalSparseVectorizerSettings,
            service_settings: LocalEmbeddingServiceSettings,
    ):
        self.settings = settings
        self.max_texts_per_request = service_settings.max_texts_per_request

        # One client per adapter, reused for every request (connection pooling).
        self.client = httpx.AsyncClient(
            base_url=f"http://{service_settings.host}:{service_settings.port}".rstrip("/"),
            headers={"X-API-Key": service_settings.api_key.get_secret_value()},
            timeout=httpx.Timeout(service_settings.request_timeout_seconds, connect=5.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )

    async def vectorize_query(self, text: str) -> SparseVector:
        response = await self.client.post(
            "/sparse/query",
            json={
                "model_key": self.settings.name,
                "text": text,
            },
        )
        response.raise_for_status()
        data = response.json()["vector"]
        return SparseVector.model_validate(data)

    async def vectorize_documents(self, texts: list[str]) -> list[SparseVector]:
        vectors: list[SparseVector] = []
        for start in range(0, len(texts), self.max_texts_per_request):
            response = await self.client.post(
                "/sparse/documents",
                json={
                    "model_key": self.settings.name,
                    "texts": texts[start:start + self.max_texts_per_request],
                },
            )
            response.raise_for_status()
            vectors.extend(SparseVector.model_validate(v) for v in response.json()["vectors"])
        return vectors

    async def shutdown(self) -> None:
        await self.client.aclose()
