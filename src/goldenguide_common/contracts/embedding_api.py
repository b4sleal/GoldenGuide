"""Pydantic request and response contracts for the local embedding HTTP API."""

from pydantic import BaseModel, Field

from goldenguide_common.contracts.vectors import SparseVector


class EmbedQueryRequest(BaseModel):
    """Request for one dense or multi-vector query embedding."""

    model_key: str = Field(min_length=1)
    text: str = Field(min_length=1)


class EmbedDocumentsRequest(BaseModel):
    """Request for dense or multi-vector embeddings for multiple documents."""

    model_key: str = Field(min_length=1)
    texts: list[str] = Field(min_length=1)


class EmbedResponse(BaseModel):
    """Response containing dense vectors or ColBERT-style multi-vectors."""

    vectors: list[list[float] | list[list[float]]]

class SparseQueryRequest(BaseModel):
    """Request for one sparse query vector."""

    model_key: str
    text: str


class SparseDocumentsRequest(BaseModel):
    """Request for sparse vectors for multiple documents."""

    model_key: str
    texts: list[str]


class SparseQueryResponse(BaseModel):
    """Response containing one sparse vector."""

    vector: SparseVector


class SparseDocumentsResponse(BaseModel):
    """Response containing sparse vectors in input order."""

    vectors: list[SparseVector]


class RerankRequest(BaseModel):
    """Request to score documents against one query."""

    model_key: str = Field(min_length=1)
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)


class RerankResponse(BaseModel):
    """Response containing one relevance score per input document."""

    scores: list[float]