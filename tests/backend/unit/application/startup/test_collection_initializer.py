"""Startup ensures payload indexes on every usable collection, new or existing, and never on a mismatch."""
from types import SimpleNamespace

import pytest

from backend.application.startup.collection_initializer import VectorCollectionInitializer
from backend.domain.ports.providers.vector_store.vector_models import (
    FILTERED_PAYLOAD_FIELDS,
    CollectionMetadata,
    PayloadIndexKind,
    VectorPayloadField,
)


def collection(key="collection_a", version=1):
    return SimpleNamespace(
        key=key,
        version=version,
        chunking=SimpleNamespace(provider="recursive", chunk_size=1500, chunk_overlap=150, separators=("\n\n",)),
        vectors=SimpleNamespace(dense=SimpleNamespace(embedding=SimpleNamespace(
            primary=SimpleNamespace(provider="minilm", dimension=384),
        ))),
    )


def metadata(version=1):
    return CollectionMetadata(
        collection_version=version, embedding_model="minilm", embedding_dimension=384,
        text_splitter_provider="recursive", chunk_size=1500, chunk_overlap=150, chunk_separators=("\n\n",),
    )


class FakeManagedStore:
    def __init__(self, stored=None):
        self.stored = stored or {}
        self.created = []
        self.indexed = []

    async def collection_exists(self, name):
        return name in self.stored

    async def get_collection_metadata(self, name):
        return self.stored[name]

    async def create_collection(self, name, config, metadata):
        self.created.append(name)

    async def ensure_payload_indexes(self, name, fields):
        self.indexed.append((name, dict(fields)))
        return list(fields)


async def test_new_collection_is_created_then_indexed():
    store = FakeManagedStore()
    await VectorCollectionInitializer(store, {"multi_sparse": collection()}).initialize()

    assert store.created == ["collection_a"]
    assert store.indexed == [("collection_a", FILTERED_PAYLOAD_FIELDS)]


async def test_existing_matching_collection_is_indexed_without_being_recreated():
    store = FakeManagedStore({"collection_a": metadata()})
    await VectorCollectionInitializer(store, {"multi_sparse": collection()}).initialize()

    assert store.created == []
    assert store.indexed == [("collection_a", FILTERED_PAYLOAD_FIELDS)]


async def test_mismatched_collection_stops_startup_before_any_index_change():
    store = FakeManagedStore({"collection_a": metadata(version=1)})
    with pytest.raises(RuntimeError, match="Version collision"):
        await VectorCollectionInitializer(store, {"multi_sparse": collection(version=2)}).initialize()

    assert store.indexed == []


def test_every_field_ingestion_and_sweeps_filter_on_is_indexed():
    assert FILTERED_PAYLOAD_FIELDS == {
        VectorPayloadField.SOURCE_ID: PayloadIndexKind.KEYWORD,
        VectorPayloadField.EMBEDDING_SOURCE: PayloadIndexKind.KEYWORD,
        VectorPayloadField.UPDATED_AT: PayloadIndexKind.DATETIME,
    }
