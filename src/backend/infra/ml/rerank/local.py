"""Reranker adapter for the local embedding service: one cross-encoder score per document."""
import httpx

from goldenguide_common.contracts.embedding_models import LocalEmbeddingServiceSettings, LocalRerankerSettings


class LocalReranker:
    """Cross-encoder reranking on the local embedding service (/rerank)."""

    def __init__(self, settings: LocalRerankerSettings, service_settings: LocalEmbeddingServiceSettings):
        self.settings = settings
        self.max_texts_per_request = service_settings.max_texts_per_request
        self.client = httpx.AsyncClient(
            base_url=f"http://{service_settings.host}:{service_settings.port}".rstrip("/"),
            headers={"X-API-Key": service_settings.api_key.get_secret_value()},
            timeout=httpx.Timeout(service_settings.request_timeout_seconds, connect=5.0),
        )

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        # Sent in groups like documents for embedding, so a large candidate set never becomes one slow request.
        scores: list[float] = []
        for start in range(0, len(documents), self.max_texts_per_request):
            response = await self.client.post(
                "/rerank",
                json={
                    "model_key": self.settings.name,
                    "query": query,
                    "documents": documents[start:start + self.max_texts_per_request],
                },
            )
            response.raise_for_status()
            scores.extend(response.json()["scores"])
        return scores

    async def shutdown(self) -> None:
        await self.client.aclose()
