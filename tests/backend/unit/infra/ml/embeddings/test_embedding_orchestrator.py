"""Embedding profiles route requests without changing text, vector shape, or failures."""

import asyncio
from unittest.mock import AsyncMock

import numpy as np
import pytest

from backend.domain.ports.providers.embedding import Embedding
from backend.domain.settings.embedding import OpenAIEmbeddingSettings
from backend.domain.settings.profiles import EmbeddingProfile
from backend.infra.ml.embeddings.gemini import normalize_rows
from backend.infra.ml.embeddings.standard_orchestrator import (
    StandardEmbeddingOrchestrator,
)


def profile(name: str) -> EmbeddingProfile:
    # Settings describe a target; no vendor SDK or API key is used by these tests.
    return EmbeddingProfile(
        primary=OpenAIEmbeddingSettings(
            name=name,
            provider="openai",
            model_name="test",
            dimension=2,
            api_key="unused",
        )
    )


@pytest.mark.parametrize(
    "vectors",
    [
        [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
        [[[1.0, 0.0]], [[0.0, 1.0], [1.0, 1.0]], [[1.0, 0.0]]],
    ],
    ids=["dense", "multivector"],
)
async def test_document_order_and_duplicate_texts_are_preserved(vectors):
    selected, other = AsyncMock(spec=Embedding), AsyncMock(spec=Embedding)
    selected.embed_documents.return_value = vectors
    service = StandardEmbeddingOrchestrator({"selected": selected, "other": other})
    texts = ["first document", "second document", "first document"]

    assert await service.embed_documents(texts, profile("selected")) == vectors
    selected.embed_documents.assert_awaited_once_with(texts)
    selected.embed_query.assert_not_awaited()
    other.embed_documents.assert_not_awaited()


async def test_query_uses_its_own_profile_and_query_operation():
    first, second = AsyncMock(spec=Embedding), AsyncMock(spec=Embedding)
    first.embed_query.return_value = [1.0, 0.0]
    second.embed_query.return_value = [0.0, 1.0]
    service = StandardEmbeddingOrchestrator({"first": first, "second": second})

    assert await service.embed_query("question", profile("first")) == [1.0, 0.0]
    assert await service.embed_query("question", profile("second")) == [0.0, 1.0]
    first.embed_query.assert_awaited_once_with("question")
    second.embed_query.assert_awaited_once_with("question")
    first.embed_documents.assert_not_awaited()
    second.embed_documents.assert_not_awaited()


@pytest.mark.parametrize(
    "operation,argument",
    [
        ("embed_query", "question"),
        ("embed_documents", ["document"]),
    ],
)
async def test_missing_provider_is_a_configuration_error(operation, argument):
    with pytest.raises(LookupError, match="missing"):
        await getattr(StandardEmbeddingOrchestrator({}), operation)(
            argument, profile("missing")
        )


@pytest.mark.parametrize(
    "operation,argument",
    [
        ("embed_query", "question"),
        ("embed_documents", ["document"]),
    ],
)
async def test_provider_failure_is_not_converted_to_an_empty_embedding(
    operation, argument
):
    provider = AsyncMock(spec=Embedding)
    failure = ConnectionError("embedding service unavailable")
    getattr(provider, operation).side_effect = failure
    service = StandardEmbeddingOrchestrator({"selected": provider})

    with pytest.raises(ConnectionError) as caught:
        await getattr(service, operation)(argument, profile("selected"))

    assert caught.value is failure


async def test_cancellation_propagates_to_the_caller():
    provider = AsyncMock(spec=Embedding)
    provider.embed_query.side_effect = asyncio.CancelledError
    service = StandardEmbeddingOrchestrator({"selected": provider})

    with pytest.raises(asyncio.CancelledError):
        await service.embed_query("question", profile("selected"))


def test_each_vector_is_normalized_on_its_own():
    rows = normalize_rows([[3.0, 4.0], [0.0, 10.0], [0.0, 0.0]])

    assert np.allclose(np.linalg.norm(rows[:2], axis=1), 1.0)
    assert rows[2] == [0.0, 0.0]  # A zero vector stays zero instead of dividing by zero.
