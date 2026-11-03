"""EmbeddingSource for Academic Calendar courses: paging, vector payloads and needs_embedding flags."""
from backend.domain.entities.ingestion_types import CourseVectorPayload, KnowledgeSourceType, VectorSource
from backend.domain.entities.wlu.course import CourseRead, CourseUpdate
from backend.domain.ports.repositories.school.query_types import CoursePageParams, CourseSortField
from backend.domain.ports.repositories.sorting import SortSpec
from backend.domain.ports.repositories.types import PrimaryKey


class CourseEmbeddingSource:
    """Academic Calendar courses for EmbeddingJob."""
    name = VectorSource.COURSES

    async def count(self, repos) -> int:
        return await repos.courses.count_courses()

    async def fetch(self, repos, offset: int, limit: int) -> list[CourseRead]:
        return await repos.courses.fetch_courses(
            page_params=CoursePageParams(limit=limit, offset=offset, order_by=[SortSpec(field=CourseSortField.ID)]),
        )

    def record_id(self, record: CourseRead) -> PrimaryKey:
        return record.id

    def needs_embedding(self, record: CourseRead) -> bool:
        return record.needs_embedding

    def payload(self, course: CourseRead) -> CourseVectorPayload:
        credits = course.credit_summary()
        return CourseVectorPayload(
            content="",  # YAML owns the structured embedded text.
            title=course.title,
            source_id=f"course_{course.id}",
            embedding_source=self.name,
            source_type=KnowledgeSourceType.WLU_PAGE,
            record_type=KnowledgeSourceType.COURSE,
            subject=course.subject,
            subject_code=course.subject_code,
            course_number=course.course_number,
            academic_year=course.academic_year,
            description=course.description,
            prereq=course.prereq,
            coreq=course.coreq,
            exclusions=course.exclusions,
            notes=course.notes,
            credits=", ".join(f"{k}: {v}" for k, v in credits.items() if v is not None) or None,
            calendar_url=course.calendar_url,
            academic_level=course.academic_level,
        )

    async def set_needs_embedding(self, repos, ids: list[PrimaryKey], value: bool) -> None:
        await repos.courses.update_courses(course_ids=ids, update_data=CourseUpdate(needs_embedding=value))
