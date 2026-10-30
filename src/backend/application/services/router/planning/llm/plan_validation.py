"""Validate and repair an LLM-produced retrieval plan against the entities actually extracted.

Pure functions: each takes a plan (and entities) and returns a new plan or raises PlanRejected.
LLMQueryPlanner falls back to fallback_plan() when any of them rejects the LLM's output.
"""
import re

import structlog

from backend.domain.entities.question import (
    SUBJECT_TYPES,
    CourseEntity,
    DisciplineEntity,
    EntityMap,
    EntityType,
)
from backend.domain.entities.retrieval_plan import (
    EvidenceRole,
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalSource,
)

logger = structlog.get_logger(__name__)


class PlanRejected(Exception):
    """The LLM's plan cannot be executed as written. Recoverable: the planner falls back.

    A dedicated type, not ValueError, so a bug inside a validator is never mistaken for a bad plan.
    """


# Which operations each source can execute.
SUPPORTED_OPERATIONS = {
    RetrievalSource.COURSES: {RetrievalOperation.LOOKUP, RetrievalOperation.FILTER, RetrievalOperation.RELATED},
    RetrievalSource.COURSE_TERMS: {RetrievalOperation.LOOKUP, RetrievalOperation.FILTER},
    RetrievalSource.WLU_PAGES: {RetrievalOperation.LOOKUP, RetrievalOperation.FILTER, RetrievalOperation.SEMANTIC},
    RetrievalSource.VECTOR: {RetrievalOperation.SEMANTIC},
}

# Sources whose entity references may use subject codes ("CP") instead of masks.
SUBJECT_REFERENCE_SOURCES = {RetrievalSource.COURSES, RetrievalSource.COURSE_TERMS, RetrievalSource.WLU_PAGES}

REGISTRATION_QUESTION = re.compile(
    r"\b("
    r"offer(?:ed|ing|s)?|"
    r"available|availability|"
    r"section(?:s)?|"
    r"register|registration|enroll|enrol|"
    r"seat(?:s)?|waitlist|"
    r"schedule|timetable|"
    r"crn|running|"
    r"taking.*(?:now|term|semester)"
    r")\b",
    re.IGNORECASE,
)


def with_requests(plan: PreLLMExtraction, requests: list[RetrievalRequest]) -> PreLLMExtraction:
    """A copy of `plan` with its retrieval requests replaced."""
    return plan.model_copy(update={"retrieval": plan.retrieval.model_copy(update={"requests": requests})})


def validate_operations(plan: PreLLMExtraction) -> PreLLMExtraction:
    """Every request uses an operation its source supports; only RELATED carries a relationship."""
    requests = []
    for request in plan.retrieval.requests:
        if request.operation not in SUPPORTED_OPERATIONS[request.source]:
            raise PlanRejected(f"Unsupported retrieval operation: {request.source.value}/{request.operation.value}")
        if request.operation == RetrievalOperation.RELATED and request.relationship is None:
            raise PlanRejected("Related retrieval requires a relationship")
        if request.operation != RetrievalOperation.RELATED and request.relationship is not None:
            request = request.model_copy(update={"relationship": None})
        requests.append(request)
    return with_requests(plan, requests)


def resolve_subject_references(plan: PreLLMExtraction, entities: EntityMap) -> PreLLMExtraction:
    """The LLM may write "CP" instead of "[DEPARTMENT1]": translate codes the extractor established.

    This is reference resolution, not fuzzy matching. Unknown codes stay unchanged and fail
    validate_entity_references.
    """
    code_masks: dict[str, str] = {}
    for mask, entity in entities.items():
        if isinstance(entity, DisciplineEntity) and entity.type in SUBJECT_TYPES and entity.code:
            code_masks.setdefault(entity.code.upper(), mask)

    def resolve(reference: str) -> str:
        normalized = reference.strip().strip("[]").upper()
        for mask in entities:
            if mask.strip("[]").upper() == normalized:
                return mask
        return code_masks.get(normalized, reference)

    def resolve_filters(filters: GlobalFilters | None) -> GlobalFilters | None:
        if filters is None or not filters.subjects:
            return filters
        return filters.model_copy(update={"subjects": [resolve(reference) for reference in filters.subjects]})

    requests = [
        request.model_copy(update={
            "entities": [
                resolve(reference) if request.source in SUBJECT_REFERENCE_SOURCES else reference
                for reference in request.entities
            ],
            "filters": resolve_filters(request.filters),
        })
        for request in plan.retrieval.requests
    ]
    plan = with_requests(plan, requests)
    return plan.model_copy(update={"global_filters": resolve_filters(plan.global_filters)})


def validate_entity_references(plan: PreLLMExtraction, entities: EntityMap) -> None:
    """Every mask the plan mentions must be one the extractor produced: the LLM may not invent entities."""
    referenced = set(plan.course_specific_filters) | set(plan.extracted_entities_logic)

    for filters in [plan.global_filters, *(request.filters for request in plan.retrieval.requests)]:
        if filters is not None:
            referenced.update(filters.subjects or [], filters.rooms or [], filters.instructors or [])
    for request in plan.retrieval.requests:
        referenced.update(request.entities)
    referenced.update(plan.conversation_context.completed_courses or [])

    unknown = referenced - set(entities)
    if unknown:
        raise PlanRejected(f"Router referenced unknown entities: {sorted(unknown)}")


def normalize_program_operations(plan: PreLLMExtraction, entities: EntityMap) -> PreLLMExtraction:
    """For program pages the entity types decide the operation: disciplines are discovered (FILTER),
    identified programs are loaded (LOOKUP). Only operations unambiguously determined by type change."""
    requests = []
    for request in plan.retrieval.requests:
        if request.source != RetrievalSource.WLU_PAGES or request.operation not in {
            RetrievalOperation.LOOKUP, RetrievalOperation.FILTER,
        }:
            requests.append(request)
            continue

        if not request.entities:
            raise PlanRejected("Structured program retrieval requires entities")

        types = {entities[mask].type for mask in request.entities}
        if types <= SUBJECT_TYPES:
            operation = RetrievalOperation.FILTER
        elif types == {EntityType.PROGRAM}:
            operation = RetrievalOperation.LOOKUP
        else:
            raise PlanRejected(f"Incompatible program entity types: {sorted(types)}")

        requests.append(request.model_copy(update={"operation": operation}))
    return with_requests(plan, requests)


def fallback_plan(question: str, entities: EntityMap) -> PreLLMExtraction:
    """A conservative plan when the LLM's is unusable: look up mentioned courses, else semantic search."""
    course_masks = [mask for mask, entity in entities.items() if isinstance(entity, CourseEntity)]

    if course_masks:
        source = (
            RetrievalSource.COURSE_TERMS
            if REGISTRATION_QUESTION.search(question)
            else RetrievalSource.COURSES
        )
        requests = [
            RetrievalRequest(source=source, operation=RetrievalOperation.LOOKUP, entities=[mask], role=EvidenceRole.REQUIRED)
            for mask in course_masks
        ]
        semantic_fallback = False
    else:
        requests = [
            RetrievalRequest(
                source=RetrievalSource.VECTOR, operation=RetrievalOperation.SEMANTIC, role=EvidenceRole.REQUIRED,
            )
        ]
        semantic_fallback = True

    logger.warning("router_fallback_used", source=requests[0].source.value, course_entities=len(course_masks))
    return PreLLMExtraction(retrieval=RetrievalPlan(requests=requests, semantic_fallback=semantic_fallback))
