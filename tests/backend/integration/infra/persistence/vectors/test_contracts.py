"""Every vector adapter must satisfy these same externally observable storage rules."""

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.domain.ports.providers.vector_store.vector_models import (
    RetrievedChunk,
    VectorPoint,
)
from goldenguide_common.contracts.vectors import SparseVector

CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)


def point(key: str, source="owned", vector=None, updated_at=CUTOFF) -> VectorPoint:
    return VectorPoint(
        id=str(uuid5(NAMESPACE_URL, key)),
        dense_vector=vector or [1.0, 0.0],
        sparse_vector=SparseVector(indices=[1], values=[1.0]),
        multi_vector=[[1.0, 0.0]],
        payload={
            "source_id": source,
            "embedding_source": "pages",
            "text": key,
            "url": f"https://example.edu/{key}",
            "updated_at": updated_at.isoformat(),
        },
    )


async def test_repeated_upsert_replaces_the_same_point_without_duplicates(vector_store):
    store, name = vector_store
    original = point("course")
    await store.upsert(name, [original])
    replacement = original.model_copy(
        update={
            "dense_vector": [0.0, 1.0],
            "payload": {**original.payload, "text": "revised"},
        }
    )
    await store.upsert(name, [replacement])
    await store.upsert(name, [replacement])

    hits = await store.search(name, dense_vector=[0.0, 1.0], score_threshold=0.9)
    assert len(hits) == 1
    assert isinstance(hits[0], RetrievedChunk)
    assert hits[0].content == "revised"
    assert hits[0].payload == replacement.payload
    assert await store.search(name, dense_vector=[1.0, 0.0], score_threshold=0.9) == []


@pytest.mark.parametrize(
    "query",
    [
        {"dense_vector": [1.0, 0.0]},
        {"sparse_vector": SparseVector(indices=[1], values=[1.0])},
        {"multivector": [[1.0, 0.0]]},
        {
            "dense_vector": [1.0, 0.0],
            "sparse_vector": SparseVector(indices=[1], values=[1.0]),
        },
    ],
    ids=["dense", "sparse", "multivector", "hybrid"],
)
async def test_search_modes_keep_payload_and_apply_filters(vector_store, query):
    store, name = vector_store
    await store.upsert(name, [point("owned"), point("foreign", source="other")])

    hits = await store.search(name, **query, filters={"source_id": "owned"})

    assert len(hits) == 1
    assert hits[0].content == "owned"
    assert hits[0].payload["url"] == "https://example.edu/owned"
    assert await store.search(name, **query, filters={"source_id": "absent"}) == []


async def test_dense_search_orders_by_relevance_and_honors_limit_and_threshold(
    vector_store,
):
    store, name = vector_store
    await store.upsert(
        name,
        [
            point("exact"),
            point("near", vector=[0.8, 0.6]),
            point("orthogonal", vector=[0.0, 1.0]),
        ],
    )

    hits = await store.search(name, dense_vector=[1.0, 0.0], limit=2)
    assert [hit.content for hit in hits] == ["exact", "near"]
    assert hits[0].score >= hits[1].score
    hits = await store.search(name, dense_vector=[1.0, 0.0], score_threshold=0.9)
    assert [hit.content for hit in hits] == ["exact"]


async def test_filters_combine_with_and_and_filter_reads_honor_limits(vector_store):
    store, name = vector_store
    other_job = point("other-job")
    other_job = other_job.model_copy(
        update={
            "payload": {**other_job.payload, "embedding_source": "courses"},
        }
    )
    await store.upsert(
        name, [point("one"), point("two"), other_job, point("foreign", source="other")]
    )
    filters = {"source_id": "owned", "embedding_source": "pages"}

    hits = await store.search(name, dense_vector=[1.0, 0.0], filters=filters)
    assert {hit.content for hit in hits} == {"one", "two"}
    assert len(await store.search_by_filter(name, filters, limit=1)) == 1
    assert len(await store.search_by_filter(name, {"source_id": "missing"})) == 0


async def test_delete_removes_only_owned_points_and_is_safe_to_repeat(vector_store):
    store, name = vector_store
    await store.upsert(name, [point("owned"), point("foreign", source="other")])

    await store.delete(name, {"source_id": "owned"})
    await store.delete(name, {"source_id": "owned"})

    hits = await store.search(name, dense_vector=[1.0, 0.0])
    assert [hit.content for hit in hits] == ["foreign"]


@pytest.mark.parametrize("operation", ["delete", "delete_older_than"])
@pytest.mark.parametrize(
    "filters", [{}, {"source_id": None}], ids=["empty", "only-null"]
)
async def test_unscoped_cleanup_is_rejected_without_losing_data(
    vector_store, operation, filters
):
    store, name = vector_store
    await store.upsert(name, [point("keep")])
    options = (
        {"timestamp_field": "updated_at", "before": CUTOFF}
        if operation == "delete_older_than"
        else {}
    )

    with pytest.raises(ValueError):
        await getattr(store, operation)(name, filters, **options)

    assert [
        hit.content for hit in await store.search(name, dense_vector=[1.0, 0.0])
    ] == ["keep"]


async def test_stale_cleanup_is_strictly_before_cutoff_and_scoped_to_owner(
    vector_store,
):
    store, name = vector_store
    old = CUTOFF - timedelta(seconds=1)
    other_job = point("other-job", updated_at=old)
    other_job = other_job.model_copy(
        update={
            "payload": {**other_job.payload, "embedding_source": "courses"},
        }
    )
    await store.upsert(
        name,
        [
            point("stale", updated_at=old),
            point("boundary"),
            point("fresh", updated_at=CUTOFF + timedelta(seconds=1)),
            point("foreign", source="other", updated_at=old),
            other_job,
        ],
    )

    filters = {"source_id": "owned", "embedding_source": "pages"}
    assert await store.delete_older_than(name, filters, "updated_at", CUTOFF) == 1
    assert await store.delete_older_than(name, filters, "updated_at", CUTOFF) == 0
    assert {
        hit.content for hit in await store.search(name, dense_vector=[1.0, 0.0])
    } == {
        "boundary",
        "fresh",
        "foreign",
        "other-job",
    }


async def test_search_requires_a_vector(vector_store):
    store, name = vector_store
    with pytest.raises(ValueError):
        await store.search(name)
