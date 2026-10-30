"""Send whole pages instead of chunks when the found pages are small enough.

Chunks answer "find the passage"; they fail "give me everything", such as a list of deadlines whose
items are spread over many chunks of which only a few make the cut. When reranking narrows the answer
to a few pages and those pages fit the budget together, the answer model gets each page complete and
in order. If they do not fit, the chunks are kept unchanged (cutting pages into sections comes later).
"""
import structlog

from backend.application.services.chatbot.db_evidence_selector import DBEvidenceSelector
from backend.application.use_cases.ingestion.wlu_pages import page_id_of
from backend.domain.entities.wlu.wlu_pages import WluPageRead
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk, VectorPayloadField
from backend.domain.ports.repositories.filters import WluPageFilter
from backend.domain.ports.repositories.school.query_types import WluPageParams
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.profiles import WholeDocumentSettings

logger = structlog.get_logger(__name__)


def source_id_of(hit: RetrievedChunk) -> str:
    """The hit's source record id ('' when the payload has none)."""
    return str((hit.payload or {}).get(VectorPayloadField.SOURCE_ID, ""))


async def load_page_texts(school_db: SchoolDB, source_ids: list[str]) -> dict[str, str]:
    """Full text of each source that is a wlu_pages row, by source_id. Missing rows are left out."""
    ids = {page_id: source_id for source_id in source_ids if (page_id := page_id_of(source_id)) is not None}
    if not ids:
        return {}
    async with school_db.start() as repos:
        pages = await repos.wlu_pages.fetch_records(
            page_params=WluPageParams(limit=len(ids)),
            filters=WluPageFilter(record_ids=list(ids)),
            view_model=WluPageRead,
        )
    return {ids[page.id]: page.content for page in pages if page.content}


async def expand_to_whole_documents(
        hits: list[RetrievedChunk],
        max_chunks: int,
        settings: WholeDocumentSettings | None,
        school_db: SchoolDB,
) -> list[RetrievedChunk]:
    """Replace the chunks of the sources in the context with their whole documents, when all fit.

    Only the first `max_chunks` hits reach the answer model, so those decide which sources count.
    Each source becomes one hit, in the order its best chunk ranked. A source with no full text (not a
    page, or its row is gone) or scoring too far below the best page keeps its chunks, which still
    count towards the budget.
    """
    if settings is None or not hits:
        return hits

    context = hits[:max_chunks]
    # Whole pages are an improvement over chunks, not a requirement: if they cannot be loaded, the
    # chunks are still valid evidence, so the answer keeps them instead of failing (as with reranking).
    try:
        texts = await load_page_texts(school_db, list(dict.fromkeys(source_id_of(hit) for hit in context)))
    except Exception as exc:
        logger.warning("whole_documents_load_failed_using_chunks", error_type=type(exc).__name__, error=str(exc))
        return hits
    if not texts:
        return hits

    # A page stored twice (e.g. imported with and without ?ref=) is one document: keep the copy that
    # ranked first, so the budget and the answer see it once.
    first_copy: dict[str, str] = {}  # page text -> source_id
    for source_id in dict.fromkeys(source_id_of(hit) for hit in context):
        if source_id in texts:
            first_copy.setdefault(texts[source_id], source_id)
    context = [hit for hit in context
               if (s := source_id_of(hit)) not in texts or first_copy[texts[s]] == s]
    sources = list(dict.fromkeys(source_id_of(hit) for hit in context))

    # Only pages close to the best page are worth sending whole; a weaker page keeps just its chunks.
    if settings.max_score_gap is not None:
        best = {s: max(hit.score for hit in context if source_id_of(hit) == s) for s in sources}
        floor = max(best.values()) - settings.max_score_gap
        texts = {s: text for s, text in texts.items() if s in best and best[s] >= floor}

    kept_chunks = [hit for hit in context if source_id_of(hit) not in texts]
    # Log fields avoid the word "token": the log redactor masks any key containing it.
    estimate = sum(DBEvidenceSelector.estimate_tokens(texts[s]) for s in sources if s in texts)
    estimate += sum(DBEvidenceSelector.estimate_tokens(hit.content) for hit in kept_chunks)
    if estimate > settings.max_tokens:
        logger.info("whole_documents_over_budget", sources=len(sources), estimate=estimate, budget=settings.max_tokens)
        return hits

    expanded: list[RetrievedChunk] = []
    for source_id in sources:
        if source_id in texts:
            first = next(hit for hit in context if source_id_of(hit) == source_id)
            text = texts[source_id]
            # context_resolver prefers payload["text"] over content, so both must carry the whole page.
            expanded.append(first.model_copy(update={"content": text, "payload": {**(first.payload or {}), "text": text}}))
        else:
            expanded.extend(hit for hit in context if source_id_of(hit) == source_id)

    logger.info("whole_documents_used", sources=len(sources), whole=len(expanded) - len(kept_chunks),
                estimate=estimate, budget=settings.max_tokens)
    return expanded
