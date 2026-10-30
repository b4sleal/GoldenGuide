"""LORIS term-section requests -> CourseTermFilters, one per (term, course or subject).

Terms are resolved in code (AcademicTermResolver), never by the LLM. Unsupported filters raise
NotImplementedError; invalid or missing anchors raise ValueError (reported as unsupported).
"""
import structlog

from backend.application.services.router.compilation.entity_resolution import (
    course_code,
    instructor_ids,
    masks_of_type,
    meeting_rooms,
    subject_code,
    unsupported_fields,
)
from backend.domain.entities.question import SUBJECT_TYPES, EntityMap, EntityType
from backend.domain.entities.retrieval_plan import (
    CourseSpecificFilters,
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.entities.wlu.academic_calendar import CourseLevel
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.ports.repositories.filters import CourseTermFilter

logger = structlog.get_logger(__name__)

MAX_FILTERS = 20


def supported_filters(params: GlobalFilters) -> GlobalFilters:
    """The restrictions term-section queries can execute."""
    return GlobalFilters(
        subjects=params.subjects, credit=params.credit, term=params.term, year=params.year, level=params.level,
        day_preference=params.day_preference, day_exclusion=params.day_exclusion,
        rooms=params.rooms, instructors=params.instructors,
    )


def supported_course_filters(specific: CourseSpecificFilters) -> CourseSpecificFilters:
    """Per-course restrictions term-section queries can execute (excluding a course is not one)."""
    return CourseSpecificFilters(
        include=specific.include if specific.include is not False else None,
        admin_action=specific.admin_action, grade=specific.grade, target_terms=specific.target_terms,
    )


class CourseTermQueryCompiler:
    """Term-section (LORIS) requests -> one CourseTermFilter per term and course/subject."""

    def __init__(self, term_resolver: AcademicTermResolver):
        self.term_resolver = term_resolver

    def compile(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
    ) -> list[CourseTermFilter]:
        if request.source != RetrievalSource.COURSE_TERMS:
            raise ValueError("Expected course_terms source")
        if request.operation not in {RetrievalOperation.LOOKUP, RetrievalOperation.FILTER}:
            raise NotImplementedError(f"Unsupported operation: {request.operation}")

        params = request.filters or GlobalFilters()
        invalid = unsupported_fields(params, supported_filters(params))
        if invalid:
            logger.warning("course_term_filters_unsupported", fields=invalid)
            raise NotImplementedError(f"Unsupported filters: {invalid}")
        if params.level and set(params.level) - set(CourseLevel):
            raise ValueError("Invalid course level")

        courses = {
            mask: course_code(mask, entities)
            for mask in masks_of_type(request.entities, entities, EntityType.COURSE)
        }
        subject_masks = [*masks_of_type(request.entities, entities, *SUBJECT_TYPES), *(params.subjects or [])]
        subjects = {subject_code(mask, entities) for mask in subject_masks}
        # Rooms and instructors may arrive as filters or as request entities, like subjects.
        rooms = meeting_rooms(
            [*(params.rooms or []), *masks_of_type(request.entities, entities, EntityType.ROOM)], entities,
        ) or None
        instructors = instructor_ids(
            [*(params.instructors or []), *masks_of_type(request.entities, entities, EntityType.INSTRUCTOR)], entities,
        ) or None

        unknown = [mask for mask in request.entities if mask not in entities]
        if unknown:
            raise ValueError(f"Unknown entity: {unknown[0]}")

        # A room or instructor is an anchor on its own ("anything in this room on Friday").
        if not courses and not subjects and not rooms and not instructors:
            raise ValueError("Registration query requires a course, subject, room or instructor")

        # Term codes for the whole request. A season without a year ("winter") means its next
        # occurrence; see AcademicTermResolver.resolve for every combination.
        terms = self.term_resolver.resolve(params.term, params.year)

        def section_filter(term_code: str, subject: str | None = None, number: str | None = None) -> CourseTermFilter:
            return CourseTermFilter(
                term_code=term_code, subject_code=subject, course_number=number,
                levels=params.level, credit=params.credit,
                day_preference=params.day_preference, day_exclusion=params.day_exclusion,
                rooms=rooms, instructor_ids=instructors,
            )

        results = []
        for mask, (subject, number) in courses.items():
            selected_terms = self.course_terms(extraction.course_specific_filters.get(mask), terms)
            results += [section_filter(term_code, subject, number) for term_code in selected_terms]

        for term_code in terms:
            results += [section_filter(term_code, subject) for subject in sorted(subjects)]
            if not courses and not subjects:
                results.append(section_filter(term_code))

        results = list({item.model_dump_json(): item for item in results}.values())
        if len(results) > MAX_FILTERS:
            raise ValueError("Too many registration queries")

        logger.info(
            "course_term_query_compiled",
            operation=request.operation.value,
            filters=len(results),
            courses=len(courses),
            subjects=len(subjects),
        )
        return results

    def course_terms(self, specific: CourseSpecificFilters | None, default: list[str]) -> list[str]:
        """Per-course terms ("CP220 in winter and CP213 in fall 2027") override the request's terms."""
        if specific is None:
            return default
        if unsupported_fields(specific, supported_course_filters(specific)):
            raise NotImplementedError("Unsupported course-specific constraints")
        if not specific.target_terms:
            return default
        return [
            code
            for target in specific.target_terms
            for code in self.term_resolver.resolve([target.term], [target.year] if target.year is not None else None)
        ]
