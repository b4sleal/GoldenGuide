"""Vector shapes exchanged between the API backend, the embedding service and the vector store."""
from pydantic import BaseModel

type DenseVector = list[float] # Dense embedding: standard embedding vector
type MultiVector = list[list[float]] # Multi-vector (ColBERT-style)
type EmbeddingVector = DenseVector | MultiVector # A provider may return either
type SparseIndices = list[int] # Sparse vector parts
type SparseValues = list[float]

class SparseVector(BaseModel):
    indices: SparseIndices
    values: SparseValues
