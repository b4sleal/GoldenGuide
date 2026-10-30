import pytest

from backend.application.services.router.planning.llm.plan_validation import (
    PlanRejected,
    fallback_plan,
    normalize_program_operations,
    resolve_subject_references,
    validate_entity_references,
    validate_operations,
)
from backend.domain.entities.retrieval_plan import (
    CourseRelationship,
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalSource,
)
from tests.backend.unit.application.services.router.factories import (
    CS,
    LH1009,
    course,
    program,
)


def plan_of(*requests: RetrievalRequest, **fields) -> PreLLMExtraction:
    return PreLLMExtraction(retrieval=RetrievalPlan(requests=list(requests)), **fields)


def request(source, operation, *entities, **fields) -> RetrievalRequest:
    return RetrievalRequest(source=source, operation=operation, entities=list(entities), **fields)


# --- validate_operations ----------------------------------------------------------------------

@pytest.mark.parametrize("source, operation", [
    (RetrievalSource.VECTOR, RetrievalOperation.LOOKUP),
    (RetrievalSource.VECTOR, RetrievalOperation.FILTER),
    (RetrievalSource.COURSE_TERMS, RetrievalOperation.RELATED),
])
def test_unsupported_operation_is_rejected(source, operation):
    with pytest.raises(PlanRejected, match="Unsupported retrieval operation"):
        validate_operations(plan_of(request(source, operation)))


def test_related_requires_relationship():
    with pytest.raises(PlanRejected, match="relationship"):
        validate_operations(plan_of(request(RetrievalSource.COURSES, RetrievalOperation.RELATED, "[COURSE1]")))


def test_relationship_is_dropped_from_non_related_requests():
    result = validate_operations(plan_of(request(
        RetrievalSource.COURSES, RetrievalOperation.LOOKUP, "[COURSE1]",
        relationship=CourseRelationship.PREREQUISITE_OF,
    )))
    assert result.retrieval.requests[0].relationship is None


# --- resolve_subject_references / validate_entity_references ---------------------------------

def test_verified_subject_code_resolves_to_mask():
    entities = {"[DEPARTMENT1]": CS}
    plan = plan_of(request(
        RetrievalSource.COURSES, RetrievalOperation.FILTER, filters=GlobalFilters(subjects=["CP"], level=[200]),
    ))

    resolved = resolve_subject_references(plan, entities)
    validate_entity_references(resolved, entities)

    filters = resolved.retrieval.requests[0].filters
    assert (filters.subjects, filters.level) == (["[DEPARTMENT1]"], [200])


def test_mask_spelling_is_normalized():
    plan = plan_of(request(RetrievalSource.COURSES, RetrievalOperation.FILTER, "department1"))
    assert resolve_subject_references(plan, {"[DEPARTMENT1]": CS}).retrieval.requests[0].entities == ["[DEPARTMENT1]"]


def test_unknown_subject_code_is_not_accepted():
    entities = {"[DEPARTMENT1]": CS}
    plan = plan_of(request(RetrievalSource.COURSES, RetrievalOperation.FILTER, filters=GlobalFilters(subjects=["FAKE"])))

    with pytest.raises(PlanRejected, match="unknown entities"):
        validate_entity_references(resolve_subject_references(plan, entities), entities)


@pytest.mark.parametrize("filters", [
    GlobalFilters(rooms=["[ROOM9]"]),
    GlobalFilters(instructors=["[INSTRUCTOR9]"]),
])
def test_invented_room_or_instructor_masks_are_rejected(filters):
    plan = plan_of(request(RetrievalSource.COURSE_TERMS, RetrievalOperation.FILTER, filters=filters))
    with pytest.raises(PlanRejected, match="unknown entities"):
        validate_entity_references(plan, {"[ROOM1]": LH1009})


# --- normalize_program_operations -------------------------------------------------------------

def test_program_operation_follows_entity_types():
    entities = {"[DEPARTMENT1]": CS, "[PROGRAM_PAGE_7]": program("Honours BSc Computer Science", 7)}
    plan = plan_of(
        request(RetrievalSource.WLU_PAGES, RetrievalOperation.LOOKUP, "[DEPARTMENT1]"),
        request(RetrievalSource.WLU_PAGES, RetrievalOperation.FILTER, "[PROGRAM_PAGE_7]"),
    )
    operations = [r.operation for r in normalize_program_operations(plan, entities).retrieval.requests]
    assert operations == [RetrievalOperation.FILTER, RetrievalOperation.LOOKUP]


def test_mixed_program_entity_types_are_rejected():
    entities = {"[DEPARTMENT1]": CS, "[COURSE1]": course("CP104")}
    plan = plan_of(request(RetrievalSource.WLU_PAGES, RetrievalOperation.FILTER, "[DEPARTMENT1]", "[COURSE1]"))
    with pytest.raises(PlanRejected, match="Incompatible"):
        normalize_program_operations(plan, entities)


# --- fallback_plan ----------------------------------------------------------------------------

def test_registration_question_falls_back_to_course_terms():
    result = fallback_plan("is computer science 213 offered right now", {"[COURSE1]": course("CP213")})
    [fallback] = result.retrieval.requests
    assert (fallback.source, fallback.operation) == (RetrievalSource.COURSE_TERMS, RetrievalOperation.LOOKUP)


def test_catalog_question_falls_back_to_courses():
    result = fallback_plan("What are the prerequisites for CP104?", {"[COURSE1]": course("CP104")})
    assert result.retrieval.requests[0].source == RetrievalSource.COURSES
    assert result.retrieval.semantic_fallback is False


def test_no_course_falls_back_to_semantic_search():
    result = fallback_plan("how do I appeal a grade", {"[DEPARTMENT1]": CS})
    assert result.retrieval.requests[0].source == RetrievalSource.VECTOR
    assert result.retrieval.semantic_fallback is True
