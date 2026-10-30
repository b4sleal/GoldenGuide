"""Vector store data: points, search hits, payload field names and collection metadata."""
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from goldenguide_common.contracts.vectors import DenseVector, MultiVector, SparseVector


class VectorPayloadField(StrEnum):
    """Payload keys the application reads or filters on, besides the record's own fields."""
    SOURCE_ID = "source_id"
    EMBEDDING_SOURCE = "embedding_source"  # Which embedding job owns the vector (VectorSource).
    CREATED_AT = "created_at"              # First embedded (UTC ISO 8601), kept across re-embeds.
    UPDATED_AT = "updated_at"              # Last embedded (UTC ISO 8601).

# Generic metadata payload stored with vectors
type Payload = dict[str, Any]

class VectorPoint(BaseModel):
    id: str
    dense_vector: DenseVector | None = None
    multi_vector: MultiVector | None = None
    sparse_vector: SparseVector | None = None
    payload: Payload = Field(default_factory=dict)

class RetrievedChunk(BaseModel):
    content: str
    score: float
    payload: Payload

class CollectionMetadata(BaseModel):
    collection_version: int
    embedding_model: str
    embedding_dimension: int
    text_splitter_provider: str
    chunk_size: int
    chunk_overlap: int
    chunk_separators: tuple[str, ...]
    model_config = ConfigDict(
        extra='ignore',      # Don't crash if Qdrant has "old" extra keys
        frozen=True,
        populate_by_name=True
    )
