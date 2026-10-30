from typing import Union

from pydantic import BaseModel, Field

from goldenguide_common.contracts.vectors import SparseVector


class EmbedQueryRequest(BaseModel):
    model_key: str = Field(min_length=1)
    text: str = Field(min_length=1)


class EmbedDocumentsRequest(BaseModel):
    model_key: str = Field(min_length=1)
    texts: list[str] = Field(min_length=1)


class EmbedResponse(BaseModel):
    vectors: list[Union[list[float], list[list[float]]]]

class SparseQueryRequest(BaseModel):
    model_key: str
    text: str


class SparseDocumentsRequest(BaseModel):
    model_key: str
    texts: list[str]


class SparseQueryResponse(BaseModel):
    vector: SparseVector


class SparseDocumentsResponse(BaseModel):
    vectors: list[SparseVector]


class RerankRequest(BaseModel):
    model_key: str = Field(min_length=1)
    query: str = Field(min_length=1)
    documents: list[str] = Field(min_length=1)


class RerankResponse(BaseModel):
    scores: list[float]