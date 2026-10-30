"""Typed settings for infrastructure providers (Qdrant, MinIO/S3, Redis, PostgreSQL, chunking)
and which instance is active for each role.
"""
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from backend.domain.common import providers_enum as Providers
from backend.domain.common.providers_enum import (
    ActiveBlobStorage,
    ActiveCache,
    ActiveDB,
    ActiveVectorStore,
)
from goldenguide_common.contracts.embedding_models import FrozenModelSettings


class FrozenInfra(BaseModel):
    model_config = ConfigDict(frozen=True)

class QdrantSettings(FrozenInfra):
    provider: Providers.VectorStoreProvider
    host: str
    port: int
    api_key: SecretStr
    # qdrant-client otherwise uses httpx's 5 s default: too short for wait=True upserts of ColBERT batches.
    timeout_seconds: int = Field(gt=0)
    # TLS to Qdrant. False for the local Docker instance; True for Qdrant Cloud or any remote host.
    https: bool = False

class MinIOSettings(FrozenInfra):
    provider: Providers.BlobStorageProvider
    host: str
    port: int
    access_key: SecretStr
    secret_key: SecretStr
    bucket: str
    # TLS to the endpoint. False for the local Docker MinIO; True for S3 or any endpoint outside the host.
    secure: bool = False

class S3Settings(FrozenInfra):
    provider: Providers.BlobStorageProvider
    # host: str
    # port: int
    # access_key: str
    # secret_key: str
    bucket: str
    region: str

class RedisSettings(FrozenInfra):
    provider: Providers.CacheProvider
    host: str
    port: int
    key_prefix: str
    max_size: int
    password: SecretStr

class DBSettings(FrozenInfra):
    provider: Providers.DBProvider
    driver: str
    host: str
    port: int
    user: SecretStr
    password: SecretStr
    database: str
    pool_size: int
    max_overflow: int
    read_only: bool

class ChunkingSettings(FrozenModelSettings):
    provider: Providers.TextSplitterProvider
    chunk_size: int = Field(gt=0)
    chunk_overlap: int = Field(ge=0)
    separators: tuple[str, ...] = Field(default_factory=tuple)

type VectorStoreSettings = QdrantSettings
type BlobStorageSettings = MinIOSettings | S3Settings
type CacheSettings = RedisSettings
type TextSplitterCatalog = Mapping[str, ChunkingSettings]

type BlobStorageCatalog = Mapping[str, BlobStorageSettings]
type DBCatalog = Mapping[str, DBSettings]
type CacheCatalog = Mapping[str, CacheSettings]
type VectorStoreCatalog = Mapping[str, VectorStoreSettings]

type ActiveBlobStorageCatalog = Mapping[ActiveBlobStorage, BlobStorageSettings]
type ActiveDBCatalog = Mapping[ActiveDB, DBSettings]
type ActiveCacheCatalog = Mapping[ActiveCache, CacheSettings]
type ActiveVectorStoreCatalog = Mapping[ActiveVectorStore, VectorStoreSettings]

