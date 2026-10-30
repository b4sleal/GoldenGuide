"""Persistence wiring: blob storage, caches and Redis-backed stores, databases and the vector store.

Catalog keys "app" and "school" select the active instance of each store (configs/catalogs/active).
"""
from dependency_injector import containers, providers

import backend.domain.common.providers_enum as Providers
from backend.core.factories.resolver import resolve_catalog_items
from backend.infra.persistence.blob_storage.app_blob_storage import AppBlobStorage
from backend.infra.persistence.caching.app.document import DocumentCache
from backend.infra.persistence.caching.app.oauth import OAuthTransactionStore
from backend.infra.persistence.caching.app.rate_limit import RateLimitStore
from backend.infra.persistence.caching.app.session import SessionStore
from backend.infra.persistence.caching.app.settings import SettingsCache
from backend.infra.persistence.caching.app_cache import AppCache
from backend.infra.persistence.caching.redis.store import RedisStore
from backend.infra.persistence.caching.school.course import CourseCache
from backend.infra.persistence.db.app.app_db import SQLAppDB
from backend.infra.persistence.db.primary_uow import PrimaryUnitOfWork
from backend.infra.persistence.db.school.school_db import SQLSchoolDB
from backend.infra.persistence.vectors.app_vector_store import AppVectorStore


class PersistenceContainer(containers.DeclarativeContainer):

    catalog = providers.Dependency()

    # ---------- Object Storage ----------

    blob_storage_providers = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.providers.blob_storage,
        provider_enum=Providers.BlobStorageProvider
    )

    active_blob_storages = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.active.blob_storage,
        provider_enum=Providers.BlobStorageProvider
    )

    app_blob_storage = providers.Singleton(
        AppBlobStorage,
        blob_storage=active_blob_storages.provided["app"]
    )

    # ---------- Cache ----------

    active_caches = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.active.cache,
        provider_enum=Providers.CacheProvider
    )

    app_cache = providers.Singleton(
        AppCache,
        cache=active_caches.provided["app"]
    )

    # Low-level transport is selected by composition; repositories remain vendor-neutral.
    app_byte_store = providers.Singleton(
        RedisStore, client=active_caches.provided["app"].client
    )
    session_store = providers.Singleton(SessionStore, store=app_byte_store)
    oauth_transaction_store = providers.Singleton(OAuthTransactionStore, store=app_byte_store)
    rate_limit_store = providers.Singleton(RateLimitStore, store=app_byte_store)
    settings_cache = providers.Singleton(SettingsCache, store=app_byte_store)
    document_cache = providers.Singleton(DocumentCache, store=app_byte_store)
    course_cache = providers.Singleton(CourseCache, store=app_byte_store)

    # ---------- Database ----------

    active_dbs = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.active.db,
        provider_enum=Providers.DBProvider
    )

    # The app database's connection. PrimaryUnitOfWork runs app and school repositories in one session
    # on it, for writes that must commit together (only valid while both live in the same database).
    primary_db = active_dbs.provided["app"]

    app_db = providers.Singleton(
        SQLAppDB,
        db=primary_db
    )

    school_db = providers.Singleton(
        SQLSchoolDB,
        db=active_dbs.provided["school"]
    )

    primary_uow = providers.Singleton(
        PrimaryUnitOfWork,
        db=primary_db,
        app_db=app_db,
        school_db=school_db,
    )

    # ---------- Vector Store ----------

    active_vector_stores = providers.Singleton(
        resolve_catalog_items,
        catalog=catalog.provided.active.vector_store,
        provider_enum=Providers.VectorStoreProvider
    )

    app_vector_store = providers.Singleton(
        AppVectorStore,
        vector_store=active_vector_stores.provided["app"],
    )
