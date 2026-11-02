"""Sentence-transformers adapter for SPLADE sparse lexical-semantic vectors.

MLM logits (``[batch, tokens, vocabulary]``) are pooled on the model's device, so only one
vocabulary-sized row per text leaves it. Memory per inference is bounded by the configured token
budget and concurrency limit, not by page or request size (docs/backend/embedding-memory-plan.md).
"""

import asyncio

import structlog
import torch
from sentence_transformers import SparseEncoder
from sentence_transformers.sparse_encoder.models import MLMTransformer, SpladePooling

from embedding_service.models.batching import token_budget_batches
from goldenguide_common.contracts.embedding_models import SpladeSparseVectorizerSettings
from goldenguide_common.contracts.vectors import SparseVector

logger = structlog.get_logger()


class SpladeSparseVectorizer:
    """Generate sparse query and document vectors for hybrid retrieval."""

    def __init__(self, settings: SpladeSparseVectorizerSettings):
        """Load SPLADE as an MLM head with max pooling of ``log1p(relu(logits))``."""

        logger.info("loading_splade_model", model_name=settings.model_name, device=settings.device)
        transformer = MLMTransformer(
            settings.model_name,
            max_seq_length=settings.max_length,
            model_args={"dtype": settings.dtype.value},
        )
        # activation "relu" is log1p(relu(x)), the same as the original SPLADE / fastembed formula.
        pooling = SpladePooling(
            pooling_strategy="max",
            activation_function="relu",
            word_embedding_dimension=transformer.get_sentence_embedding_dimension(),
            chunk_size=settings.pooling_chunk_size,
        )
        self.model = SparseEncoder(modules=[transformer, pooling], device=settings.device)
        self.max_length = settings.max_length
        self.max_batch_tokens = settings.max_batch_tokens
        self.inference_slots = asyncio.Semaphore(settings.max_concurrent_inferences)

    async def vectorize_query(self, text: str) -> SparseVector:
        """Vectorize one query and return its sparse indices and values."""

        return (await self.vectorize_documents([text]))[0]

    async def vectorize_documents(self, texts: list[str]) -> list[SparseVector]:
        """Vectorize documents in token-budget batches while preserving input order."""

        async with self.inference_slots:
            return await asyncio.to_thread(self._vectorize, texts)

    def _vectorize(self, texts: list[str]) -> list[SparseVector]:
        token_counts = [
            len(ids)
            for ids in self.model.tokenizer(texts, truncation=True, max_length=self.max_length)["input_ids"]
        ]
        vectors: dict[int, SparseVector] = {}
        for batch in token_budget_batches(token_counts, self.max_batch_tokens):
            rows = self.model.encode(
                [texts[index] for index in batch],
                batch_size=len(batch),
                convert_to_tensor=True,
                convert_to_sparse_tensor=False,
                show_progress_bar=False,
            )
            for index, row in zip(batch, rows, strict=True):
                vectors[index] = _to_sparse_vector(row)
        return [vectors[index] for index in range(len(texts))]


def _to_sparse_vector(row: torch.Tensor) -> SparseVector:
    """Keep only the non-zero vocabulary weights; select on the device, copy the few to the host."""

    indices = torch.nonzero(row, as_tuple=True)[0]
    return SparseVector(indices=indices.tolist(), values=row[indices].float().tolist())
