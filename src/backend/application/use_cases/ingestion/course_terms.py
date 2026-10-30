"""EmbeddingSource for LORIS course terms (registration sections): paging, payloads and flags."""
from backend.domain.entities.ingestion_types import CourseTermVectorPayload, KnowledgeSourceType, VectorSource
from backend.domain.entities.wlu.loris_registration import CourseTermRead, CourseTermUpdate, RegistrationDescription
from backend.domain.ports.repositories.filters import CourseTermFilter
from backend.domain.ports.repositories.school.query_types import CourseTermParams, CourseTermSortField
from backend.domain.ports.repositories.sorting import SortSpec
from backend.domain.ports.repositories.types import PrimaryKey


def split_requirements(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    if RegistrationDescription.SEPARATOR not in value:
        return value.strip() or None, None
    description, menu = value.split(RegistrationDescription.SEPARATOR, 1)
    return description.strip() or None, menu.strip() or None


class CourseTermEmbeddingSource:
    """LORIS course terms (registration sections) for EmbeddingJob."""
    name = VectorSource.COURSE_TERMS

    async def count(self, repos) -> int:
        return await repos.course_terms.count_course_terms()

    async def fetch(self, repos, offset: int, limit: int) -> list[CourseTermRead]:
        return await repos.course_terms.fetch_course_terms(
            page_params=CourseTermParams(limit=limit, offset=offset, order_by=[SortSpec(field=CourseTermSortField.ID)]),
            filters=CourseTermFilter(),
            view_model=CourseTermRead,
        )

    def record_id(self, record: CourseTermRead) -> PrimaryKey:
        return record.id

    def needs_embedding(self, record: CourseTermRead) -> bool:
        return record.needs_embedding

    def payload(self, term: CourseTermRead) -> CourseTermVectorPayload:
        prereq_desc, prereq_menu = split_requirements(term.prereq)
        coreq_desc, coreq_menu = split_requirements(term.coreq)
        return CourseTermVectorPayload(
            content="",
            title=term.title,
            source_id=f"course_term_{term.id}",
            embedding_source=self.name,
            source_type=KnowledgeSourceType.LORIS_REGISTRATION,
            record_type=KnowledgeSourceType.COURSE.value,
            course_id=term.course_id,
            subject_code=term.subject_code,
            course_number=term.course_number,
            subject=term.subject,
            term_code=term.term_code,
            term_name=term.term_name or term.term_code,
            section_code=term.section_code,
            crn=term.crn,
            description=term.description,
            prereq_description=prereq_desc,
            prereq_menu=prereq_menu,
            coreq_description=coreq_desc,
            coreq_menu=coreq_menu,
            exclusions=term.exclusions,
            restrictions=term.restrictions,
            notes=term.notes,
            instructional_method=term.instructional_method,
        )

    async def set_needs_embedding(self, repos, ids: list[PrimaryKey], value: bool) -> None:
        await repos.course_terms.update_course_terms(course_term_ids=ids, update_data=CourseTermUpdate(needs_embedding=value))
