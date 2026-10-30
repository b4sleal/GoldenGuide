"""Vector payloads per knowledge source (course, course term, WLU page, document) and their source enums."""
from enum import StrEnum
from pydantic import BaseModel


class DocMimeType(StrEnum):
    PDF = "application/pdf"
    TXT = "text/plain"
    HTML = "text/html"
    MARKDOWN = "text/markdown"


class DocType(StrEnum):
    PDF = "pdf"
    TXT = "txt"
    HTML = "html"
    MARKDOWN = "markdown"


class KnowledgeSourceType(StrEnum):
    WLU_PAGE = "wlu_page"
    COURSE = "course"
    LORIS_REGISTRATION = "loris_registration"
    DOC = "doc"


class VectorSource(StrEnum):
    """What produced a vector, so one source's vectors can be found or swept without knowing their ids."""
    WLU_PAGES = "wlu_pages"
    COURSES = "courses"
    COURSE_TERMS = "course_terms"
    DOCUMENTS = "documents"


class KnowledgeVectorPayload(BaseModel):
    content: str
    title: str | None = None
    source_id: str
    source_type: KnowledgeSourceType
    record_type: str
    embedding_source: VectorSource


class CourseVectorPayload(KnowledgeVectorPayload):
    subject_code: str
    course_number: str
    subject: str | None = None
    academic_year: str
    description: str | None = None
    prereq: str | None = None
    coreq: str | None = None
    exclusions: str | None = None
    notes: str | None = None
    credits: str | None = None
    calendar_url: str | None = None


class CourseTermVectorPayload(KnowledgeVectorPayload):
    course_id: int
    subject_code: str
    course_number: str
    subject: str | None = None
    term_code: str
    term_name: str | None = None
    section_code: str | None = None
    crn: str
    description: str | None = None
    prereq_description: str | None = None
    prereq_menu: str | None = None
    coreq_description: str | None = None
    coreq_menu: str | None = None
    exclusions: str | None = None
    restrictions: str | None = None
    notes: str | None = None
    instructional_method: str | None = None


class WluPageVectorPayload(KnowledgeVectorPayload):
    url: str
    site_name: str


class DocumentVectorPayload(KnowledgeVectorPayload):
    filename: str
    doc_type: DocType
    mime_type: DocMimeType
