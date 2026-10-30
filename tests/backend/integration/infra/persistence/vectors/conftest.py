"""Adapter setup lives here; the vector requirements are written once in test_contracts.py."""

import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from qdrant_client import models

from backend.domain.common.providers_enum import VectorStoreProvider
from backend.domain.settings.providers import QdrantSettings
from backend.infra.persistence.vectors.app_vector_store import AppVectorStore
from backend.infra.persistence.vectors.qdrant.store import QDrantStore

# Register each adapter's setup once. Parametrizing the enum makes an unregistered provider fail.
VECTOR_STORE_FIXTURES = {VectorStoreProvider.QDRANT: "qdrant_store"}


@pytest.fixture(params=list(VectorStoreProvider), ids=lambda provider: provider.value)
def vector_store(request):
    assert request.param in VECTOR_STORE_FIXTURES, (
        f"Add a contract fixture for {request.param}"
    )
    return request.getfixturevalue(VECTOR_STORE_FIXTURES[request.param])


@pytest.fixture
async def qdrant_store(infra_service_url):
    url = urlsplit(infra_service_url("QDRANT_TEST_URL"))
    if (
        url.scheme != "http"
        or not url.hostname
        or url.username
        or url.path not in ("", "/")
    ):
        pytest.fail("QDRANT_TEST_URL must be a disposable HTTP test endpoint")
    store = QDrantStore(
        QdrantSettings(
            name="contract-tests",
            provider="qdrant",
            host=url.hostname,
            port=url.port or 6333,
            api_key=os.getenv("QDRANT_TEST_API_KEY", ""),
            timeout_seconds=15,
        )
    )
    name = f"gg_contract_test_{uuid4().hex}"
    try:
        # Collection mechanics are provider-specific; none leak into the behavioral suite.
        await store.client.create_collection(
            collection_name=name,
            vectors_config={
                "dense": models.VectorParams(size=2, distance=models.Distance.COSINE),
                "colbert": models.VectorParams(
                    size=2,
                    distance=models.Distance.COSINE,
                    multivector_config=models.MultiVectorConfig(
                        comparator=models.MultiVectorComparator.MAX_SIM
                    ),
                ),
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
        yield AppVectorStore(store), name
    finally:
        try:
            if await store.client.collection_exists(name):
                await store.client.delete_collection(name)
        finally:
            await store.shutdown()
