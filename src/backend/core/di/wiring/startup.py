"""Startup and provisioning steps.

Two lists, split by one rule: **only the provision job writes; API replicas only check.**
    provisioning      run once per deploy by `python -m backend.core.startup.provision`
                      (database migrations run just before these, see provision.py)
    api_startup       run by every API replica in the FastAPI lifespan; read-only

That way N replicas starting together cannot race on schema/collection/bucket creation, and the API
never needs create/alter privileges in production.
"""
from dependency_injector import containers, providers

from backend.application.startup.blob_storage_initializer import BlobStorageInitializer
from backend.application.startup.collection_initializer import (
    VectorCollectionInitializer,
)
from backend.infra.persistence.db.migrations.schema_check import SchemaVersionCheck


class StartupContainer(containers.DeclarativeContainer):

    catalog = providers.Dependency()
    persistence = providers.DependenciesContainer()

    # ---------- Provision job (create if missing) ----------

    # Create configured object-storage buckets.
    blob_storage_initializer = providers.Singleton(
        BlobStorageInitializer,
        initializers=persistence.blob_storage_providers,
    )

    # Create vector collections, or verify existing ones match the configured version.
    vector_collection_initializer = providers.Singleton(
        VectorCollectionInitializer,
        vector_store=persistence.active_vector_stores.provided["app"],
        vector_collections=catalog.provided.profiles.vector_collection,
    )

    provisioning = providers.List(
        blob_storage_initializer,
        vector_collection_initializer,
    )

    # ---------- API startup (read-only checks) ----------

    # The database must already be at the latest migration.
    schema_check = providers.Singleton(
        SchemaVersionCheck,
        db=persistence.primary_db,
    )

    api_startup = providers.List(
        schema_check,
    )
