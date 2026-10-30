"""The application boundary preserves constraints, domain results, and storage failures."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from backend.domain.ports.providers.vector_store.port import VectorStore
from backend.domain.ports.providers.vector_store.vector_models import (
    RetrievedChunk,
    VectorPoint,
)
from backend.infra.persistence.vectors.app_vector_store import AppVectorStore
from goldenguide_common.contracts.vectors import SparseVector


async def test_search_preserves_all_modalities_constraints_and_source_payload():
    adapter = AsyncMock(spec=VectorStore)
    expected = [
        RetrievedChunk(
            content="course text",
            score=0.9,
            payload={
                "source_id": "course-1",
                "url": "https://example.edu/course",
                "text": "course text",
            },
        )
    ]
    adapter.search.return_value = expected
    options = {
        "name": "courses",
        "dense_vector": [1.0, 0.0],
        "sparse_vector": SparseVector(indices=[3], values=[0.5]),
        "multivector": [[1.0, 0.0]],
        "limit": 7,
        "filters": {"source_id": "course-1"},
        "score_threshold": 0.25,
    }

    assert await AppVectorStore(adapter).search(**options) == expected
    adapter.search.assert_awaited_once_with(**options)


async def test_upsert_preserves_point_identity_vectors_and_provenance():
    adapter = AsyncMock(spec=VectorStore)
    points = [
        VectorPoint(
            id="point-1",
            dense_vector=[1.0, 0.0],
            payload={
                "source_id": "course-1",
                "embedding_source": "courses",
                "text": "course text",
            },
        )
    ]

    await AppVectorStore(adapter).upsert("courses", points)

    adapter.upsert.assert_awaited_once_with(name="courses", points=points)


async def test_cleanup_preserves_ownership_cutoff_and_deleted_count():
    adapter = AsyncMock(spec=VectorStore)
    adapter.delete_older_than.return_value = 3
    before = datetime(2026, 1, 1, tzinfo=UTC)
    filters = {"source_id": "course-1", "embedding_source": "courses"}

    assert (
        await AppVectorStore(adapter).delete_older_than(
            "courses", filters, "updated_at", before
        )
        == 3
    )
    adapter.delete_older_than.assert_awaited_once_with(
        name="courses",
        filters=filters,
        timestamp_field="updated_at",
        before=before,
    )


async def test_filter_read_and_scoped_delete_preserve_selection():
    adapter = AsyncMock(spec=VectorStore)
    adapter.search_by_filter.return_value = ["opaque adapter record"]
    store = AppVectorStore(adapter)
    filters = {"source_id": "course-1"}

    assert await store.search_by_filter("courses", filters, limit=2) == [
        "opaque adapter record"
    ]
    await store.delete("courses", filters)

    adapter.search_by_filter.assert_awaited_once_with(
        name="courses", filters=filters, limit=2
    )
    adapter.delete.assert_awaited_once_with(name="courses", filters=filters)


@pytest.mark.parametrize(
    "operation,kwargs",
    [
        ("upsert", {"points": []}),
        ("search", {"dense_vector": [1.0, 0.0]}),
        ("search_by_filter", {"filters": {"source_id": "course-1"}}),
        ("delete", {"filters": {"source_id": "course-1"}}),
        (
            "delete_older_than",
            {
                "filters": {"source_id": "course-1"},
                "timestamp_field": "updated_at",
                "before": datetime(2026, 1, 1, tzinfo=UTC),
            },
        ),
    ],
)
async def test_storage_failure_is_not_reported_as_an_empty_result_or_success(
    operation, kwargs
):
    adapter = AsyncMock(spec=VectorStore)
    failure = ConnectionError("vector service unavailable")
    getattr(adapter, operation).side_effect = failure

    with pytest.raises(ConnectionError) as caught:
        await getattr(AppVectorStore(adapter), operation)(name="courses", **kwargs)

    assert caught.value is failure
