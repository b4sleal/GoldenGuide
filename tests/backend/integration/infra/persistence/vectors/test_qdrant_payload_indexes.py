"""Qdrant payload indexes: created once for the filtered fields, idempotent, never silently retyped."""
import pytest
from qdrant_client.http.models import PayloadSchemaType

from backend.domain.ports.providers.vector_store.vector_models import (
    FILTERED_PAYLOAD_FIELDS,
    PayloadIndexKind,
    VectorPayloadField,
)
from tests.backend.integration.infra.persistence.vectors.test_contracts import point


def indexed_types(schema):
    return {field: info.data_type for field, info in schema.items()}


async def test_existing_points_get_every_filtered_index_once_and_stay_searchable(qdrant_store):
    app_store, name = qdrant_store
    store = app_store.vector_store
    await app_store.upsert(name, [point("before-index")])

    created = await store.ensure_payload_indexes(name, FILTERED_PAYLOAD_FIELDS)
    again = await store.ensure_payload_indexes(name, FILTERED_PAYLOAD_FIELDS)

    assert set(created) == set(FILTERED_PAYLOAD_FIELDS)
    assert again == []
    schema = indexed_types((await store.client.get_collection(name)).payload_schema)
    assert schema == {
        VectorPayloadField.SOURCE_ID.value: PayloadSchemaType.KEYWORD,
        VectorPayloadField.EMBEDDING_SOURCE.value: PayloadSchemaType.KEYWORD,
        VectorPayloadField.UPDATED_AT.value: PayloadSchemaType.DATETIME,
        VectorPayloadField.ACADEMIC_LEVEL.value: PayloadSchemaType.KEYWORD,
    }
    hits = await app_store.search_by_filter(name, {VectorPayloadField.SOURCE_ID: "owned"})
    assert len(hits) == 1


async def test_field_indexed_with_another_type_is_reported_not_replaced(qdrant_store):
    app_store, name = qdrant_store
    store = app_store.vector_store
    await store.client.create_payload_index(
        collection_name=name, field_name=VectorPayloadField.UPDATED_AT.value,
        field_schema=PayloadSchemaType.KEYWORD, wait=True,
    )

    with pytest.raises(RuntimeError, match="updated_at"):
        await store.ensure_payload_indexes(name, {VectorPayloadField.UPDATED_AT: PayloadIndexKind.DATETIME})

    schema = indexed_types((await store.client.get_collection(name)).payload_schema)
    assert schema[VectorPayloadField.UPDATED_AT.value] == PayloadSchemaType.KEYWORD
