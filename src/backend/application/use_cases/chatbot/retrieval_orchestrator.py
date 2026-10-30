"""Coordinate everything that happens between a student's question and the answer prompt.

    question
      -> QueryRouter plan:      which records to fetch (structured requests, maybe semantic)
      -> enrichment             add course + course-term lookups for every course mentioned
      -> _execute               run structured requests against Postgres, collect evidence + outcomes
      -> RAGContextResolver     optional semantic (vector) search, build the context text
      -> tables                 section and listing tables placed with {{TABLE:n}} (evidence_tables.py)
      -> limitations            tell the answer model what could not be answered (retrieval_limitations.py)
"""
import json
import time

import structlog

from backend.application.services.chatbot.db_evidence_selector import DBEvidenceSelector
from backend.application.services.chatbot.retrieval_router import RetrievalProfileRouter
from backend.application.services.router.router import QueryRouter
from backend.application.services.router.retrieval.structured_retriever import StructuredRetriever
from backend.application.use_cases.chatbot.context_resolver import RAGContextResolver
from backend.application.use_cases.chatbot.evidence_tables import build_tables, prompt_records, table_catalog_text
from backend.application.use_cases.chatbot.retrieval_limitations import (
    context_limit_note,
    limitation_notes,
    render_limitations,
    semantic_failure_note,
)
from backend.domain.entities.question import CourseEntity, DisciplineEntity, EntityMap, EntityType, ProgramEntity
from backend.domain.entities.retrieval import Evidence, RetrievalOutcome, RetrievalStatus
from backend.domain.settings.ai_behavior import ResolvedRAGContext
from backend.domain.settings.profiles import DBEvidenceProfile
from backend.domain.entities.retrieval_plan import (
    EvidenceRole,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)

logger = structlog.get_logger(__name__)

# Upper bounds that keep the prompt size predictable.
_RECORDS_PER_REQUEST = 50
_MAX_FACTUAL_RECORDS = 70
# Planned FILTER requests are listings ("all CP courses": 77 rows); the table shows every row
# while the prompt still sees at most _MAX_FACTUAL_RECORDS.
_LISTING_RECORDS_PER_REQUEST = 200


def elapsed_ms(since: float) -> int:
    """Milliseconds since a time.perf_counter() reading."""
    return round((time.perf_counter() - since) * 1000)


class AcademicRetrievalOrchestrator:
    """Coordinate structured and semantic retrieval."""

    def __init__(
            self,
            query_router: QueryRouter,
            factual_retriever: StructuredRetriever,
            rag_context_resolver: RAGContextResolver,
            retrieval_router: RetrievalProfileRouter,
    ):
        self.query_router = query_router
        self.structured = factual_retriever
        self.rag = rag_context_resolver
        self.retrieval_router = retrieval_router
        self.db_evidence_selector = DBEvidenceSelector()

    @staticmethod
    def _expand_entities(entities: EntityMap) -> EntityMap:
        """Add a subject entity for each course (CP220 -> subject CP), so subject-level
        requests can use courses the student mentioned."""
        expanded = dict(entities)

        for mask, entity in entities.items():
            if not isinstance(entity, CourseEntity):
                continue

            # Only codes shaped like two letters + three digits (e.g. CP220) have a derivable subject.
            code = entity.normalized
            if len(code) < 5 or not code[:2].isalpha() or not code[2:5].isdigit():
                continue

            expanded[f"[DERIVED_SUBJECT_{mask[1:-1]}]"] = DisciplineEntity(
                type=EntityType.SUBJECT,
                code=code[:2],
                canonical=code[:2],
                derived_from=mask,
            )

        return expanded

    @staticmethod
    def _register_program_entities(records: list[Evidence], entities: EntityMap) -> None:
        """Expose discovered program pages as entities, so later requests can look them up by id."""
        for record in records:
            if not record.source_id.startswith("wlu_page:"):
                continue

            raw_id = record.source_id.split(":", 1)[1]
            if not raw_id.isdecimal():
                continue

            record_id = int(raw_id)
            entities[f"[PROGRAM_PAGE_{record_id}]"] = ProgramEntity(canonical=record.title, record_id=record_id)

    @staticmethod
    def _request_key(request: RetrievalRequest) -> str:
        """Identity of a request, ignoring its role, so the same lookup never runs twice."""
        return json.dumps(request.model_dump(mode="json", exclude={"role"}), sort_keys=True)

    @staticmethod
    def _enrich_with_course_lookups(requests: list[RetrievalRequest], raw_entities: EntityMap) -> list[RetrievalRequest]:
        """Add course-details and course-offering lookups for every course the student mentioned.

        The router sometimes omits an obvious lookup ("is CP220 hard?" still needs CP220's record).
        These additions are not part of the student's plan: retrieval_limitations reports them
        only on system failure. Course-term lookups without filters use the current term.
        """
        enriched = list(requests)
        course_masks = [mask for mask, entity in raw_entities.items() if isinstance(entity, CourseEntity)]

        for source in (RetrievalSource.COURSES, RetrievalSource.COURSE_TERMS):
            for mask in course_masks:
                already_planned = any(
                    r.source == source and r.operation == RetrievalOperation.LOOKUP and mask in r.entities
                    for r in enriched
                )
                if not already_planned:
                    enriched.append(RetrievalRequest(
                        source=source,
                        operation=RetrievalOperation.LOOKUP,
                        entities=[mask],
                        role=EvidenceRole.REQUIRED,
                    ))

        return enriched

    async def _execute(
            self,
            requests: list[RetrievalRequest],
            extraction: PreLLMExtraction,
            entities: EntityMap,
            evidence: dict[str, Evidence],
            outcomes: list[RetrievalOutcome],
            executed: set[str],
            db_evidence_profile: DBEvidenceProfile,
            limit: int,
            planned_keys: set[str] | None = None,
            table_records: dict[str, bool] | None = None,
    ) -> bool:
        """Run structured requests. Evidence goes into `evidence`, one outcome per request into `outcomes`.

        Records that can be shown as a table go into `table_records` (source_id -> requested):
        every course-term section, so sections are always a table rather than retyped text, and
        planned listings. `requested` is True when a planned request returned the record.

        Returns True if the plan asked for semantic (vector) search, which RAGContextResolver runs.
        A failing request is recorded and skipped, so one broken source never sinks the whole answer;
        the outcome makes sure the gap is reported (retrieval_limitations.py).
        """
        semantic_requested = False

        for request in requests:
            # Step 1: skip duplicates (the router and enrichment can plan the same lookup).
            key = self._request_key(request)
            if key in executed:
                continue
            executed.add(key)

            # Step 2: vector requests are handled later by RAGContextResolver, not here.
            if request.source == RetrievalSource.VECTOR:
                if request.operation == RetrievalOperation.SEMANTIC:
                    semantic_requested = True
                else:
                    outcomes.append(RetrievalOutcome(
                        request=request,
                        status=RetrievalStatus.UNSUPPORTED,
                        error="Unsupported vector operation",
                    ))
                continue

            # Step 3: run the structured query, then trim each record to the detail level the
            # profile allows (token budget).
            planned_listing = request.operation == RetrievalOperation.FILTER and key in (planned_keys or set())
            request_limit = _LISTING_RECORDS_PER_REQUEST if planned_listing else limit
            try:
                # One record beyond the limit proves more matched (reported as "search limited").
                records = await self.structured.retrieve(
                    request=request,
                    extraction=extraction,
                    entities=entities,
                    limit=request_limit + 1,
                )
                truncated = len(records) > request_limit
                records = self.db_evidence_selector.select(
                    evidence=records[:request_limit], profile=db_evidence_profile,
                )
            except (ValueError, NotImplementedError) as exc:
                # The plan could not be turned into a query (unsupported filter, unresolved entity) or
                # its records exceed the evidence budget. Expected and recoverable: recorded as
                # UNSUPPORTED, logged without a traceback.
                outcomes.append(RetrievalOutcome(
                    request=request,
                    status=RetrievalStatus.UNSUPPORTED,
                    error=str(exc)[:200],
                ))
                logger.warning(
                    "retrieval_unsupported",
                    source=request.source.value,
                    operation=request.operation.value,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
                continue
            except Exception:
                # The data source itself failed (database down, timeout). Recorded as FAILED and
                # logged with the traceback; the answer will say this part could not be checked.
                outcomes.append(RetrievalOutcome(
                    request=request,
                    status=RetrievalStatus.FAILED,
                    error="Repository retrieval failed",
                ))
                logger.exception(
                    "retrieval_failed",
                    source=request.source.value,
                    operation=request.operation.value,
                )
                continue

            outcomes.append(RetrievalOutcome(
                request=request,
                status=RetrievalStatus.COMPLETED,
                count=len(records),
                truncated_at=request_limit if truncated else None,
            ))

            if request.source == RetrievalSource.WLU_PAGES and request.operation == RetrievalOperation.FILTER:
                self._register_program_entities(records, entities)

            # Sections are always tabled; an automatic lookup's table (e.g. sections fetched for a
            # prerequisites question) is only shown if the answer places it.
            if table_records is not None and (request.source == RetrievalSource.COURSE_TERMS or planned_listing):
                requested = key in (planned_keys or set())
                for record in records:
                    table_records[record.source_id] = table_records.get(record.source_id, False) or requested

            # Step 4: merge into the evidence map. The same record can come from several requests;
            # keep the more useful copy (primary over supporting; a detailed program lookup wins).
            detailed_program_lookup = (
                request.source == RetrievalSource.WLU_PAGES
                and request.operation == RetrievalOperation.LOOKUP
            )
            for record in records:
                current = evidence.get(record.source_id)
                if current is None or detailed_program_lookup or (record.primary and not current.primary):
                    evidence[record.source_id] = record

            logger.info(
                "retrieval_completed",
                source=request.source.value,
                operation=request.operation.value,
                count=len(records),
            )

        return semantic_requested

    async def resolve_context(self, question: str, top_k: int = 8) -> ResolvedRAGContext:
        """Build the full answer context for `question`, including any retrieval limitations."""
        # Step 1: choose the retrieval profile and let the router plan the requests.
        # "Pre-LLM" stage: entity extraction plus the router LLM's plan.
        started = time.perf_counter()
        profile = self.retrieval_router.route_question(question)
        extraction, raw_entities = await self.query_router.route(question)
        entities = self._expand_entities(raw_entities)
        routing_ms = elapsed_ms(started)

        # Step 2: remember which requests the student's question planned, then add automatic lookups.
        planned = list(extraction.retrieval.requests)
        planned_keys = {self._request_key(request) for request in planned}
        requests = self._enrich_with_course_lookups(planned, raw_entities)

        # Step 3: run the structured requests.
        evidence: dict[str, Evidence] = {}
        outcomes: list[RetrievalOutcome] = []
        executed: set[str] = set()
        table_records: dict[str, bool] = {}
        started = time.perf_counter()
        semantic = await self._execute(
            requests=requests,
            extraction=extraction,
            entities=entities,
            evidence=evidence,
            outcomes=outcomes,
            executed=executed,
            db_evidence_profile=profile.db_evidence,
            limit=_RECORDS_PER_REQUEST,
            planned_keys=planned_keys,
            table_records=table_records,
        )
        structured_ms = elapsed_ms(started)

        # Step 4: fall back to semantic search when the plan allows it and nothing structured was found.
        if extraction.retrieval.semantic_fallback and not evidence:
            semantic = True

        # Tables the answer can place with markers, built from the exact records (evidence_tables.py).
        # Evidence keeps retrieval order, so table rows follow the database's section ordering.
        tables = build_tables(
            [record for record in evidence.values() if record.source_id in table_records],
            requested_ids={source_id for source_id, requested in table_records.items() if requested},
        )

        # Primary evidence first, capped so the prompt stays within budget. Tabled records use their
        # short table text, so the answer refers to the table instead of retyping it.
        ordered = prompt_records(
            sorted(evidence.values(), key=lambda item: not item.primary)[:_MAX_FACTUAL_RECORDS], tables,
        )

        logger.info(
            "academic_retrieval_complete",
            requests=len(executed),
            factual_records=len(ordered),
            semantic=semantic,
            completed=sum(o.status == RetrievalStatus.COMPLETED for o in outcomes),
            failed=sum(o.status == RetrievalStatus.FAILED for o in outcomes),
            unsupported=sum(o.status == RetrievalStatus.UNSUPPORTED for o in outcomes),
        )

        # Step 5: semantic search (if enabled) and context assembly.
        started = time.perf_counter()
        context = await self.rag.resolve_context(
            question=question,
            top_k=top_k,
            factual=ordered,
            semantic_enabled=semantic,
        )
        logger.info(
            "retrieval_timings",
            routing_ms=routing_ms,          # Pre-LLM: entity extraction + router LLM plan.
            structured_ms=structured_ms,    # Postgres lookups.
            vector_search_ms=elapsed_ms(started) if semantic else None,  # Embed, search, rerank, whole pages.
        )

        # Step 6: tell the answer model which parts of the question could not be answered,
        # so it says so instead of answering from unrelated records.
        notes = limitation_notes(outcomes, planned_keys, self._request_key, entities)
        if context.semantic_failed:
            notes.append(semantic_failure_note())
        if len(evidence) > _MAX_FACTUAL_RECORDS:
            notes.append(context_limit_note(shown=_MAX_FACTUAL_RECORDS, total=len(evidence)))

        if not tables and not notes:
            return context

        logger.info("retrieval_context_extended", tables=len(tables), limitations=len(notes))
        return context.model_copy(update={
            "context_text": context.context_text + table_catalog_text(tables) + render_limitations(notes),
            "tables": tables,
        })
