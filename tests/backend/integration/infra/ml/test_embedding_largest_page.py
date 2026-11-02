"""Manual stress test: embed the largest ``wlu_pages`` page against the running embedding service.

Reproduces the 2026-11-01 container crash (docs/backend/embedding-memory-plan.md). Opt-in
only: it reads real page data and can take down the embedding container, so it skips unless
both variables are set (it never fails CI for missing services):

    EMBEDDING_STRESS_DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/goldenguide
    EMBEDDING_STRESS_SERVICE_URL=http://localhost:8001

The API key comes from LOCAL_EMBEDDING_SERVICE__API_KEY (loaded from .env). The database is
only read, inside a READ ONLY transaction; nothing is written to Postgres or Qdrant.
Run with ``-s`` to see the page size; watch ``docker stats`` alongside.
"""

import asyncio
import os
from pathlib import Path

import httpx
import pytest
from omegaconf import OmegaConf
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.domain.settings.providers import ChunkingSettings
from backend.infra.ml.text.recursive_splitter import RecursiveTextSplitter

SPLITTER_CONFIG = Path("configs/catalogs/providers/text_splitter.yml")
# Same request size the backend clients send.
BATCH_SIZE = OmegaConf.load("configs/base/embedding_service.yml").local_embedding_service.max_texts_per_request
# Same order as ingestion: dense, sparse, multi-vector.
MODELS = ["embed:minilm", "sparse:splade", "embed:colbert"]
LARGEST_PAGE = text(
    "SELECT id, url, content FROM wlu_pages ORDER BY length(content) DESC LIMIT 1"
)


def _required(variable: str) -> str:
    value = os.getenv(variable)
    if not value:
        pytest.skip(f"{variable} is not set; this stress test is opt-in")
    return value


def split_like_ingestion(content: str, profile: str) -> list[str]:
    """Split with the production splitter and chunk profile (no enrichment prefix)."""
    catalog = OmegaConf.to_container(OmegaConf.load(SPLITTER_CONFIG), resolve=True)
    settings = ChunkingSettings.model_validate({"name": profile, **catalog["catalog"]["providers"]["text_splitter"][profile]})
    return RecursiveTextSplitter(settings).split(content)


@pytest.fixture(scope="module")
def largest_page_chunks() -> list[str]:
    """Chunks of the largest page, split as ingestion splits it."""
    async def fetch():
        engine = create_async_engine(_required("EMBEDDING_STRESS_DATABASE_URL"))
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                return (await connection.execute(LARGEST_PAGE)).one()
        finally:
            await engine.dispose()

    page_id, url, content = asyncio.run(fetch())
    chunks = split_like_ingestion(content, os.getenv("EMBEDDING_STRESS_CHUNK_PROFILE", "large"))
    print(f"\nlargest page id={page_id} url={url} chars={len(content)} chunks={len(chunks)}")
    return chunks


@pytest.mark.parametrize("model", MODELS)
def test_service_embeds_largest_page_without_crashing(largest_page_chunks, model):
    """Every request of the page succeeds; a crash surfaces as a ConnectError/ReadError."""
    api_key = _required("LOCAL_EMBEDDING_SERVICE__API_KEY")
    with httpx.Client(
        base_url=_required("EMBEDDING_STRESS_SERVICE_URL"),
        headers={"X-API-Key": api_key},
        timeout=180,
    ) as client:
        kind, model_key = model.split(":", 1)
        path = "/sparse/documents" if kind == "sparse" else "/embed/documents"
        try:
            for start in range(0, len(largest_page_chunks), BATCH_SIZE):
                batch = largest_page_chunks[start:start + BATCH_SIZE]
                response = client.post(path, json={"model_key": model_key, "texts": batch})
                response.raise_for_status()
                assert len(response.json()["vectors"]) == len(batch)
        except httpx.TransportError as exc:
            pytest.fail(f"{model}: embedding service dropped the connection ({exc!r}); it likely crashed")
