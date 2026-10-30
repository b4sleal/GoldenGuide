"""Second-stage ranking of semantic search hits.

The vector search fuses dense, sparse and ColBERT similarity: good at finding candidates, but it cannot
tell "important dates and deadlines" from a page that merely lists many dates. A cross-encoder reads the
question and each candidate together and scores how well the candidate answers it, so the passages that
reach the answer model are the relevant ones rather than the most similar-looking ones.
"""
import structlog

from backend.domain.ports.providers.reranker import RerankerOrchestrator
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk
from backend.domain.settings.profiles import RetrievalRerank

logger = structlog.get_logger(__name__)


def drop_duplicate_chunks(hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """First occurrence of each chunk text, in order.

    The same text can be stored under several records (a page imported twice, e.g. with and without
    a ?ref= query string); without this, copies take several of the few slots the answer model gets.
    """
    seen: set[str] = set()
    unique = []
    for hit in hits:
        if hit.content not in seen:
            seen.add(hit.content)
            unique.append(hit)
    return unique


async def rerank_hits(
        question: str,
        hits: list[RetrievedChunk],
        rerank: RetrievalRerank | None,
        reranker: RerankerOrchestrator,
) -> list[RetrievedChunk]:
    """The best `rerank.top_k` hits by cross-encoder score, highest first; `hits` unchanged without rerank.

    A reranker failure keeps the search order (logged): the hits are still valid evidence, only less
    precisely ordered, so the answer degrades instead of failing.
    """
    if rerank is None or not hits:
        return hits

    try:
        scores = await reranker.rerank(question, [hit.content for hit in hits], rerank.reranker)
    except Exception as exc:
        logger.warning("rerank_failed_using_search_order", error_type=type(exc).__name__, error=str(exc))
        return hits[:rerank.top_k]

    # One score per hit, or the pairing is wrong: zip would silently drop or misattribute hits.
    if len(scores) != len(hits):
        logger.warning("rerank_score_count_mismatch_using_search_order", hits=len(hits), scores=len(scores))
        return hits[:rerank.top_k]

    ranked = sorted(zip(scores, hits), key=lambda pair: pair[0], reverse=True)[:rerank.top_k]
    if rerank.max_score_gap is not None:
        floor = ranked[0][0] - rerank.max_score_gap
        ranked = [(score, hit) for score, hit in ranked if score >= floor]
    return [hit.model_copy(update={"score": score}) for score, hit in ranked]
