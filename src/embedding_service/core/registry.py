from goldenguide_common.contracts.embedding_models import (
    LocalEmbeddingProvider,
    LocalRerankerProvider,
    LocalSparseVectorizerProvider,
)
from embedding_service.models.embedding.fastembed_colbert import FastEmbedColbertEmbedding
from embedding_service.models.embedding.minilm import MiniLMEmbedding
from embedding_service.models.reranker.cross_encoder import CrossEncoderReranker
from embedding_service.models.vectorizer.splade import SpladeSparseVectorizer

VECTORIZER_REGISTRY = {
    LocalEmbeddingProvider.MINILM: MiniLMEmbedding,
    LocalEmbeddingProvider.FASTEMBED_COLBERT: FastEmbedColbertEmbedding,
    LocalSparseVectorizerProvider.SPLADE: SpladeSparseVectorizer,
    LocalRerankerProvider.CROSS_ENCODER: CrossEncoderReranker,
}

def build_model_registry(catalog):
    registry = {}

    for name, settings in catalog.items():
        if settings.provider not in VECTORIZER_REGISTRY:
            raise ValueError(f"Unsupported local embedding provider: {settings.provider}")

        registry[name] = VECTORIZER_REGISTRY[settings.provider](settings)

    return registry
