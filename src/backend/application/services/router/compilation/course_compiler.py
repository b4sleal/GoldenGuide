"""Academic Calendar course requests (LOOKUP / FILTER / RELATED) -> CourseFilters.

Unsupported filters or relationships raise NotImplementedError and invalid entities raise ValueError,
so the orchestrator reports the gap instead of running a broader query than the student asked for.
"""
import structlog

from backend.application.services.router.compilation.entity_resolution import (
    course_code,
    subject_code,
    unsupported_fields,
)
from backend.domain.entities.question import EntityMap
from backend.domain.entities.retrieval_plan import (
    CourseRelationship,
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.ports.repositories.filters import CourseFilter
from backend.domain.settings.institution import InstitutionProfile

logger = structlog.get_logger(__name__)


class CourseQueryCompiler:
    """Course-catalog requests -> CourseFilters. Catalog courses have no terms, days, rooms or instructors."""

    def __init__(self, institution: InstitutionProfile):
        # Every catalog query is scoped to the institution this deployment serves.
        self.institution = institution.code

    def compile(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
    ) -> list[CourseFilter]:
        if request.source != RetrievalSource.COURSES:
            # A wiring error, not an empty result: never let it read as "no courses found".
            raise ValueError(f"Expected courses source, got {request.source.value}")

        params = request.filters or GlobalFilters()
        invalid = unsupported_fields(params, GlobalFilters(subjects=params.subjects, level=params.level))
        if invalid:
            logger.warning("course_filters_unsupported", fields=invalid)
            raise NotImplementedError(f"Unsupported course filters: {invalid}")

        if request.operation == RetrievalOperation.LOOKUP:
            filters = [
                CourseFilter(institution=self.institution, subject_code=subject, course_number=number)
                for subject, number in (course_code(mask, entities) for mask in request.entities)
            ]

        elif request.operation == RetrievalOperation.RELATED:
            filters = [self.related(request.relationship, *course_code(mask, entities)) for mask in request.entities]

        elif request.operation == RetrievalOperation.FILTER:
            # Subjects may arrive as filters or as request entities, depending on the planner. Every
            # request entity must be a subject: anything else would be silently dropped from the query.
            masks = [*(params.subjects or []), *request.entities]
            codes = list(dict.fromkeys(subject_code(mask, entities) for mask in masks))
            filters = [
                CourseFilter(institution=self.institution, subject_code=code, levels=params.level)
                for code in codes or [None]
            ]

        else:
            raise NotImplementedError(f"Unsupported course operation: {request.operation}")

        logger.info("course_query_compiled", operation=request.operation.value, filters=len(filters))
        return filters

    def related(self, relationship: CourseRelationship | None, subject: str, number: str) -> CourseFilter:
        code = f"{subject}{number}"
        if relationship == CourseRelationship.PREREQUISITE_OF:
            return CourseFilter(institution=self.institution, prerequisite_of=code)
        if relationship == CourseRelationship.COREQUISITE_OF:
            return CourseFilter(institution=self.institution, corequisite_of=code)
        if relationship == CourseRelationship.EXCLUDES:
            return CourseFilter(institution=self.institution, excludes_course=code)
        if relationship is None:
            raise ValueError("Related queries require a relationship")
        # REQUIRES is intentionally not mapped: it needs prerequisite parsing or a requirements table.
        raise NotImplementedError(f"Unsupported relationship: {relationship}")
