"""The catalog section of the configuration: providers, profiles, active instances, text enrichment,
institution, router and scraping settings.

These models assemble typed catalogs into the YAML tree. They do not construct
providers or resolve active instances; the composition root owns that work.
"""
from pydantic import BaseModel, ConfigDict

from backend.domain.settings import providers
from backend.domain.settings.ai_behavior import RetrievalProfileCatalog
from backend.domain.settings.embedding import EmbeddingCatalog
from goldenguide_common.contracts.embedding_models import (
    LocalEmbeddingCatalog,
    LocalRerankerCatalog,
    LocalSparseVectorizerCatalog,
)
from backend.domain.settings.institution import InstitutionProfile
from backend.domain.settings.llm import LLMCatalog
from backend.domain.settings.profiles import (
    DBEvidenceCatalog,
    RetrievalTextCatalog,
    VectorCollectionCatalog,
    VectorRetrievalCatalog,
    WluLexicon,
)
from backend.domain.settings.router import RouterSettings
from backend.domain.settings.scraping import ScrapingCatalog


class FrozenConfig(BaseModel):
    model_config = ConfigDict(frozen=True)


class ActiveCatalog(FrozenConfig):
    """Named infrastructure instances selected for this deployment."""

    blob_storage: providers.ActiveBlobStorageCatalog
    db: providers.ActiveDBCatalog
    cache: providers.ActiveCacheCatalog
    vector_store: providers.ActiveVectorStoreCatalog


class ProviderCatalogs(FrozenConfig):
    """Available infrastructure and ML providers, including local model definitions."""

    blob_storage: providers.BlobStorageCatalog
    db: providers.DBCatalog
    cache: providers.CacheCatalog
    vector_store: providers.VectorStoreCatalog
    llm: LLMCatalog
    embedding: EmbeddingCatalog
    local_embedding: LocalEmbeddingCatalog
    text_splitter: providers.TextSplitterCatalog
    local_sparse_vectorizer: LocalSparseVectorizerCatalog
    local_reranker: LocalRerankerCatalog


class ProfileCatalogs(FrozenConfig):
    """Reusable retrieval and evidence profiles referenced by application workflows."""

    retrieval_profiles: RetrievalProfileCatalog
    vector_collection: VectorCollectionCatalog
    retrieval: VectorRetrievalCatalog
    db_evidence: DBEvidenceCatalog


class TextEnrichmentCatalog(FrozenConfig):
    """Vocabulary and text templates used to prepare retrieval input."""

    wlu_lexicon: WluLexicon
    retrieval_text: RetrievalTextCatalog


class CatalogSettings(FrozenConfig):
    """Validated catalogs, institution context, and workflow configuration."""

    providers: ProviderCatalogs
    profiles: ProfileCatalogs
    active: ActiveCatalog
    text_enrichment: TextEnrichmentCatalog
    institution: InstitutionProfile
    router: RouterSettings
    scraping: ScrapingCatalog
