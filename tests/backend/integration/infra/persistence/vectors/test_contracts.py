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
HYBRID = {
    "dense_vector": [1.0, 0.0],
    "sparse_vector": SparseVector(indices=[1], values=[1.0]),
}
HYBRID_COLBERT = {**HYBRID, "multivector": [[1.0, 0.0]]}
# Above the Qdrant adapter's minimum candidate limit (200).
OUTRANKING_POINTS = 250


def point(
    key: str, source="owned", vector=None, updated_at=CUTOFF, multi_vector=None
) -> VectorPoint:
    return VectorPoint(
        id=str(uuid5(NAMESPACE_URL, key)),
        dense_vector=vector or [1.0, 0.0],
        sparse_vector=SparseVector(indices=[1], values=[1.0]),
        multi_vector=multi_vector or [[1.0, 0.0]],
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
        HYBRID,
        {"dense_vector": [1.0, 0.0], "multivector": [[1.0, 0.0]]},
        HYBRID_COLBERT,
    ],
    ids=["dense", "sparse", "multivector", "hybrid", "dense-colbert", "hybrid-colbert"],
)
async def test_search_modes_keep_payload_and_apply_filters(vector_store, query):
    store, name = vector_store
    await store.upsert(name, [point("owned"), point("foreign", source="other")])

    hits = await store.search(name, **query, filters={"source_id": "owned"})

    assert len(hits) == 1
    assert hits[0].content == "owned"
    assert hits[0].payload["url"] == "https://example.edu/owned"
    assert await store.search(name, **query, filters={"source_id": "absent"}) == []


@pytest.mark.parametrize("query", [HYBRID, HYBRID_COLBERT], ids=["hybrid", "hybrid-colbert"])
async def test_filtered_hybrid_search_finds_matches_outranked_by_other_points(
    vector_store, query
):
    store, name = vector_store
    # More better-matching foreign points than any candidate limit: an unfiltered candidate
    # search would return only those, and the filter would then leave nothing.
    foreign = [point(f"foreign-{i}", source="other") for i in range(OUTRANKING_POINTS)]
    owned = point("owned", vector=[0.6, 0.8]).model_copy(
        update={"sparse_vector": SparseVector(indices=[2], values=[1.0])}
    )
    await store.upsert(name, [*foreign, owned])

    hits = await store.search(name, **query, limit=5, filters={"source_id": "owned"})

    assert [hit.content for hit in hits] == ["owned"]


async def test_colbert_reranks_the_dense_and_sparse_candidates(vector_store):
    store, name = vector_store
    # Dense search prefers token-mismatch; the ColBERT score alone decides the final order.
    await store.upsert(
        name,
        [
            point("token-mismatch", multi_vector=[[1.0, 0.0]]),
            point("token-match", vector=[0.8, 0.6], multi_vector=[[0.0, 1.0]]),
        ],
    )

    hits = await store.search(name, **{**HYBRID, "multivector": [[0.0, 1.0]]})

    assert [hit.content for hit in hits] == ["token-match", "token-mismatch"]
    assert hits[0].score > hits[1].score


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
