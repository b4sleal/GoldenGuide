"""Seeding and query helpers for course-term integration tests."""
from sqlalchemy import select

from backend.domain.entities.wlu.course import CourseCreate, CourseMetadata
from backend.domain.entities.wlu.loris_registration import CourseFaculty, CourseMeetingTime, CourseTermCreate
from backend.domain.ports.repositories.filters import CourseTermFilter
from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps
from backend.infra.persistence.db.school.base.course_page_repo import SqlCourseRepository
from backend.infra.persistence.db.school.base.course_term_repo import SqlCourseTermRepository
from backend.infra.persistence.db.school.filters import CourseTermFilterTranslator
from backend.infra.persistence.db.school.school_tables import CourseTerm

TERM_CODE = "202609"


def section(crn: str, meetings=(), faculty=(), **fields) -> CourseTermCreate:
    return CourseTermCreate(
        course_id=0, term_code=TERM_CODE, crn=crn, subject="Computer Science", subject_code="CP", course_number="220",
        meetings=[CourseMeetingTime(**meeting) for meeting in meetings],
        faculty=[CourseFaculty(**person) for person in faculty],
        **fields,
    )


async def seed(session, sections: list[CourseTermCreate]) -> None:
    """Persist sections (and the course they belong to) through the repositories under test."""
    [course_id] = await SqlCourseRepository(session, PostgresDialectOps()).upsert_courses([CourseCreate(
        academic_year="2026/2027", institution="WLU", subject="Computer Science", subject_code="CP",
        course_number="220", campus="Waterloo", metadata_json=CourseMetadata(),
    )])
    await SqlCourseTermRepository(session, PostgresDialectOps()).upsert_course_terms(
        [term.model_copy(update={"course_id": course_id}) for term in sections]
    )


async def matching_crns(session, filters: CourseTermFilter) -> set[str]:
    rows = await session.execute(CourseTermFilterTranslator.apply(select(CourseTerm.crn), filters))
    return set(rows.scalars().all())
