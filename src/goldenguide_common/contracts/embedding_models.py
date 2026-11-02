"""Settings for the local embedding service and its models, shared by the API backend and the service."""
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class FrozenModelSettings(BaseModel):
    name: str
    model_config = ConfigDict(frozen=True)


class LocalEmbeddingProvider(StrEnum):
    MINILM = "minilm"
    FASTEMBED_COLBERT = "fastembed_colbert"

class LocalSparseVectorizerProvider(StrEnum):
    SPLADE = "splade"

class LocalRerankerProvider(StrEnum):
    CROSS_ENCODER = "cross_encoder"


class MiniLMEmbeddingSettings(FrozenModelSettings):
    provider: LocalEmbeddingProvider
    model_name: str
    dimension: int
    device: str
    runtime: str

class FeColbertEmbeddingSettings(FrozenModelSettings):
    provider: LocalEmbeddingProvider
    model_name: str
    dimension: int
    device: str
    runtime: str

class TorchDType(StrEnum):
    FLOAT32 = "float32"
    FLOAT16 = "float16"


class SpladeSparseVectorizerSettings(FrozenModelSettings):
    """SPLADE inference limits. Peak device memory per inference is about
    ``max_batch_tokens x vocabulary size x bytes(dtype)``, independent of page or request size."""

    provider: LocalSparseVectorizerProvider
    model_name: str
    max_length: int = Field(gt=0, description="Tokens per text; longer texts are truncated.")
    max_batch_tokens: int = Field(gt=0, description="Padded tokens (texts x longest text) per inference batch.")
    pooling_chunk_size: int = Field(gt=0, description="Sequence positions pooled at a time.")
    max_concurrent_inferences: int = Field(gt=0)
    dtype: TorchDType
    device: str
    runtime: str

    @model_validator(mode="after")
    def _one_text_fits_a_batch(self) -> SpladeSparseVectorizerSettings:
        if self.max_batch_tokens < self.max_length:
            raise ValueError("max_batch_tokens must be at least max_length so any text fits one batch")
        return self

class CrossEncoderRerankerSettings(FrozenModelSettings):
    """A cross-encoder reads the query and a passage together and scores how well the passage answers it."""
    provider: LocalRerankerProvider
    model_name: str
    max_length: int = Field(gt=0, description="Tokens per query + passage pair; longer pairs are truncated.")
    batch_size: int = Field(gt=0)
    device: str
    runtime: str

type LocalRerankerSettings = CrossEncoderRerankerSettings
type LocalRerankerCatalog = Mapping[str, LocalRerankerSettings]

type LocalSparseVectorizerSettings = SpladeSparseVectorizerSettings
type LocalEmbeddingSettings = MiniLMEmbeddingSettings | FeColbertEmbeddingSettings

type LocalEmbeddingCatalog = Mapping[str, LocalEmbeddingSettings]
type LocalSparseVectorizerCatalog = Mapping[str, LocalSparseVectorizerSettings]


class LocalEmbeddingServiceSettings(BaseModel):
    """One service instance's connection details and request limits. Never log api_key."""

    model_config = ConfigDict(frozen=True)
    api_key: SecretStr
    # Which models this service instance loads: those whose own `runtime` matches. A typo fails at boot
    # instead of starting a service with no models.
    runtime: Literal["cpu", "gpu"]
    host: str
    port: int
    request_timeout_seconds: float = Field(gt=0)
    # Documents are sent in groups so one long page never becomes one request that outlives the timeout.
    max_texts_per_request: int = Field(gt=0)
    memory_log_interval_seconds: float = Field(default=60, gt=0)
