"""Profiles that combine providers into behavior: vector collections, retrieval, reranking,
DB evidence budgets, text enrichment and the WLU lexicon.
"""
from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.entities.ingestion_types import KnowledgeSourceType
from backend.domain.settings.embedding import EmbeddingSettings
from goldenguide_common.contracts.embedding_models import LocalRerankerSettings, LocalSparseVectorizerSettings
from backend.domain.settings.llm import LLMSettings
from backend.domain.settings.providers import ChunkingSettings

type RetrievalTextEntries = Mapping[str, list[str]]
type FacultyEntries = Mapping[str, LexiconEntry]
type DepartmentEntries = Mapping[str, LexiconEntry]
type RegistrationNotesEntries = Mapping[str, LexiconEntry]

type VectorRetrievalCatalog =  Mapping[str, VectorRetrievalSettings]
type VectorCollectionCatalog = Mapping[str, VectorCollectionSettings]
type RetrievalTextCatalog = Mapping[str, RetrievalTextProfile]
type DBEvidenceCatalog = Mapping[str, DBEvidenceProfile]


class FrozenProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

class EmbeddingProfile(FrozenProfile):
    primary: EmbeddingSettings

class LLMProfile(FrozenProfile):
    primary: LLMSettings
    fallback: list[LLMSettings] = Field(default_factory=list)

class SparseVectorProfile(FrozenProfile):
    primary: LocalSparseVectorizerSettings

class DenseVectorSettings(FrozenProfile):
    embedding: EmbeddingProfile
    distance: str

class SparseVectorSettings(FrozenProfile):
    vectorizer: SparseVectorProfile

class MultiVectorSettings(FrozenProfile):
    embedding: EmbeddingProfile
    size: int
    distance: str

class VectorCollectionVectors(FrozenProfile):
    dense: DenseVectorSettings | None = None
    sparse: SparseVectorSettings | None = None
    multi_vector: MultiVectorSettings | None = None

class VectorCollectionSettings(FrozenProfile):
    name: str
    version: int = 1
    key: str
    chunking: ChunkingSettings
    text_enrichment: RetrievalTextProfile
    vectors: VectorCollectionVectors

class RetrievalSearch(FrozenProfile):
    top_k: int = Field(gt=0)
    alpha: float | None = None

class RerankerProfile(FrozenProfile):
    primary: LocalRerankerSettings

class RetrievalRerank(FrozenProfile):
    """Re-score the search candidates with `reranker` and keep the best `top_k`.

    max_score_gap drops hits scoring more than that below the best one (reranker logits), so weakly
    related pages do not ride along with the page that answers the question. None keeps all top_k.
    """
    top_k: int = Field(gt=0)
    reranker: RerankerProfile
    max_score_gap: float | None = Field(default=None, gt=0)

class WholeDocumentSettings(FrozenProfile):
    """Send the found pages whole, instead of their chunks, when together they fit `max_tokens`.

    max_score_gap: only pages whose best hit scores within this of the best page's are sent whole;
    weaker pages keep just their chunks (cheap), instead of a whole page of mostly unrelated text.
    Scores are the reranker's (logits). None sends every found page whole.
    """
    max_tokens: int = Field(gt=0)
    max_score_gap: float | None = Field(default=None, gt=0)

class VectorRetrievalSettings(FrozenProfile):
    name: str
    search: RetrievalSearch
    rerank: RetrievalRerank | None = None
    whole_documents: WholeDocumentSettings | None = None

class LexiconEntry(FrozenProfile):
    canonical: str
    course_code: str | None = None
    aliases: list[str]

class WluLexicon(FrozenProfile):
    faculties: FacultyEntries
    departments: DepartmentEntries
    registration_notes: RegistrationNotesEntries

type RetrievalTextProfile = Mapping[KnowledgeSourceType, RetrievalTextEntries]

class RetrievalProfile(FrozenProfile):
    name: str
    vector_retrieval: VectorRetrievalSettings
    vector_collection: VectorCollectionSettings
    llm: LLMProfile
    db_evidence: DBEvidenceProfile
    fallback: list["RetrievalProfile"] = Field(default_factory=list)

class DBEvidenceSettings(FrozenProfile):
    max_records: int | None = Field(default=None, gt=0)
    max_tokens: int = Field(gt=0)

class DBEvidenceProfile(FrozenProfile):
    name: str
    detailed: DBEvidenceSettings # Return all contents
    compact: DBEvidenceSettings # Return only the most relevant and condensed contents (e.g. short description)
    minimal: DBEvidenceSettings # Return only the named features (name, title, etc)