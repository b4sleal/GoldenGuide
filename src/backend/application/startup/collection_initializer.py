"""Startup step: make sure every configured vector collection exists and matches its configuration.

A missing collection is created. An existing one must carry the same metadata (version, embedding
model and dimension, chunking): vectors built with different settings cannot be searched together, so
a mismatch stops startup instead of silently mixing incompatible vectors.
"""
import structlog
from pydantic import ValidationError

from backend.domain.settings.profiles import VectorCollectionCatalog
from backend.domain.ports.providers.vector_store.vector_models import CollectionMetadata
from backend.domain.ports.providers.vector_store.port import ManagedVectorStore

logger = structlog.get_logger()


class VectorCollectionInitializer:
    """Ensures vector collections exist and match expected configuration."""

    def __init__(
            self,
            vector_store: ManagedVectorStore,
            vector_collections: VectorCollectionCatalog
    ):
        self.vector_store = vector_store
        self.vector_collections = vector_collections

    async def initialize(self):
        for profile_name, vc in self.vector_collections.items():
            collection_name = vc.key

            logger.info("initializing_vector_collections", collection_name=collection_name)

            # The metadata records the dense embedding, so a collection without one cannot be checked.
            if vc.vectors.dense is None:
                raise RuntimeError(f'Collection "{collection_name}" ({profile_name}) has no dense vector configured.')
            embedding = vc.vectors.dense.embedding.primary

            expected_metadata = CollectionMetadata(
                collection_version=vc.version,
                embedding_model=embedding.provider,
                embedding_dimension=embedding.dimension,
                text_splitter_provider=vc.chunking.provider,
                chunk_size=vc.chunking.chunk_size,
                chunk_overlap=vc.chunking.chunk_overlap,
                chunk_separators=vc.chunking.separators
            )

            exists = await self.vector_store.collection_exists(collection_name)

            if not exists:
                await self.vector_store.create_collection(
                    name=collection_name,
                    config=vc,
                    metadata=expected_metadata
                )

                continue

            try:
                actual_metadata = await self.vector_store.get_collection_metadata(
                    collection_name
                )
            except ValidationError as e:
                # Stored metadata predates the current CollectionMetadata shape.
                logger.exception(
                    "outdated_vector_collection_schema",
                    profile=profile_name,
                    collection_name=collection_name,
                    expected_metadata=expected_metadata.model_dump(),
                )

                raise RuntimeError(
                    f'Collection "{collection_name}" metadata is outdated or invalid. '
                    f'Increase the collection version, delete the collection, or migrate it to the current version.'
                ) from e

            if actual_metadata != expected_metadata:
                # Name the differing settings, so the fix (config rollback or version bump) is obvious.
                expected, actual = expected_metadata.model_dump(), actual_metadata.model_dump()
                changed = {key: {"stored": actual[key], "configured": expected[key]}
                           for key in expected if expected[key] != actual.get(key)}
                raise RuntimeError(
                    f'Version collision for collection "{collection_name}": {changed}. '
                    f'Roll back the config or increase the collection version.'
                )

            logger.info("vector_collection_initialized", collection_name=collection_name)
