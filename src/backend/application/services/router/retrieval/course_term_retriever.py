"""Retrieve LORIS term sections for a compiled request (paged, capped) and render them as Evidence."""
import structlog

from backend.application.services.router.compilation.course_term_compiler import (
    CourseTermQueryCompiler,
)
from backend.application.services.router.evidence.course_term_evidence import (
    course_term_evidence,
)
from backend.domain.entities.question import EntityMap
from backend.domain.entities.retrieval import Evidence
from backend.domain.entities.retrieval_plan import (
    EvidenceRole,
    PreLLMExtraction,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.entities.wlu.loris_registration import CourseTermRead
from backend.domain.ports.repositories.school.query_types import CourseTermParams
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.domain.settings.institution import InstitutionProfile

logger = structlog.get_logger(__name__)


class CourseTermRetriever:
    """Retrieve term-specific registration sections."""

    source = RetrievalSource.COURSE_TERMS

    PAGE_SIZE = 50
    MAX_RECORDS = 250

    def __init__(
            self,
            school_db: SchoolDB,
            compiler: CourseTermQueryCompiler,
            institution: InstitutionProfile,
    ):
        self.school_db = school_db
        self.compiler = compiler
        self.registration_url = str(institution.registration_url)

    async def retrieve(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
            limit: int = 50,
    ) -> list[Evidence]:
        if not 1 <= limit <= self.MAX_RECORDS:
            raise ValueError("Invalid retrieval limit")

        filters = self.compiler.compile(
            request=request,
            extraction=extraction,
            entities=entities,
        )

        if not filters:
            raise ValueError("No executable CourseTerm filters")

        results: dict[int, CourseTermRead] = {}

        # At most `limit` records: the caller asks for one more than it needs to detect truncation.
        async with self.school_db.start() as repos:
            for course_filter in filters:
                offset = 0
                page_size = min(self.PAGE_SIZE, limit)

                while len(results) < limit:
                    rows = await repos.course_terms.fetch_course_terms(
                        page_params=CourseTermParams(
                            limit=page_size,
                            offset=offset,
                        ),
                        filters=course_filter,
                    )

                    for row in rows:
                        results[row.id] = row

                    if len(rows) < page_size:
                        break

                    offset += len(rows)

                if len(results) >= limit:
                    break

        terms = sorted(
            results.values(),
            key=lambda term: (
                term.term_code,
                term.subject_code,
                term.course_number,
                term.section_code or "",
                term.id,
            ),
        )[:limit]

        logger.info(
            "course_term_retrieval_completed",
            filters=len(filters),
            records=len(terms),
        )

        return course_term_evidence(
            terms, primary=request.role == EvidenceRole.REQUIRED, registration_url=self.registration_url,
        )
