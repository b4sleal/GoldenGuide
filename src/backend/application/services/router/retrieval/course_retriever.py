"""Retrieve Academic Calendar courses for a compiled course request and render them as Evidence."""
import structlog

from backend.application.services.router.compilation.course_compiler import (
    CourseQueryCompiler,
)
from backend.application.services.router.evidence.course_evidence import course_evidence
from backend.domain.entities.question import EntityMap
from backend.domain.entities.retrieval import Evidence
from backend.domain.entities.retrieval_plan import (
    EvidenceRole,
    PreLLMExtraction,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.entities.wlu.course import CourseRead
from backend.domain.ports.repositories.school.query_types import CoursePageParams
from backend.domain.ports.repositories.school.school_db import SchoolDB

logger = structlog.get_logger(__name__)

MAX_RECORDS = 250


class CourseRetriever:
    """Retrieve Academic Calendar course definitions."""

    source = RetrievalSource.COURSES

    def __init__(
            self,
            school_db: SchoolDB,
            compiler: CourseQueryCompiler,
    ):
        self.school_db = school_db
        self.compiler = compiler

    async def retrieve(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
            limit: int = 50,
    ) -> list[Evidence]:
        if not 1 <= limit <= MAX_RECORDS:
            raise ValueError("Invalid course retrieval limit")

        filters = self.compiler.compile(
            request=request,
            extraction=extraction,
            entities=entities,
        )

        if not filters:
            raise ValueError("No executable course filters")

        # Keyed by id: several filters (e.g. two subjects) can return the same course once.
        results: dict[int, CourseRead] = {}

        async with self.school_db.start() as repos:
            for course_filter in filters:
                courses = await repos.courses.fetch_courses(
                    page_params=CoursePageParams(limit=limit),
                    filters=course_filter,
                )

                for course in courses:
                    results[course.id] = course

        courses = sorted(
            results.values(),
            key=lambda course: (
                course.subject_code,
                course.course_number,
                course.academic_year,
            ),
        )

        primary = request.role == EvidenceRole.REQUIRED

        logger.info(
            "course_retrieval_completed",
            filters=len(filters),
            records=len(courses),
        )

        return [course_evidence(course, primary) for course in courses[:limit]]
