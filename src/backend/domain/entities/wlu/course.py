"""Academic Calendar courses: the stable course identity (per academic year), its metadata and views."""
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class FrozenCourse(BaseModel):
    model_config = ConfigDict(frozen=True)


class CourseField(StrEnum):
    ID = "id"
    ACADEMIC_YEAR = "academic_year"
    INSTITUTION = "institution"
    SUBJECT = "subject"
    SUBJECT_CODE = "subject_code"
    COURSE_NUMBER = "course_number"
    CAMPUS = "campus"
    TITLE = "title"
    CALENDAR_URL = "calendar_url"
    DESCRIPTION = "description"
    PREREQ = "prereq"
    COREQ = "coreq"
    EXCLUSIONS = "exclusions"
    NOTES = "notes"
    CREDIT_MIN = "credit_min"
    CREDIT_MAX = "credit_max"
    CREDIT_UNIT = "credit_unit"
    METADATA_JSON = "metadata_json"
    CONTENT_HASH = "content_hash"
    NEEDS_EMBEDDING = "needs_embedding"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class CourseMetadata(FrozenCourse):
    model_config = ConfigDict(extra="allow")

    department_contact: str | None = None
    faculty: str | None = None
    has_lab: bool | None = None
    departments: list[str] | None = None
    external_links: list[str] | None = None

class CourseBase(FrozenCourse):
    IDENTITY_FIELDS: ClassVar[tuple[CourseField, ...]] = (
        CourseField.ACADEMIC_YEAR,
        CourseField.INSTITUTION,
        CourseField.SUBJECT_CODE,
        CourseField.COURSE_NUMBER,
    )

    EMBED_FIELDS: ClassVar[tuple[CourseField, ...]] = (
        CourseField.SUBJECT,
        CourseField.TITLE,
        CourseField.DESCRIPTION,
        CourseField.PREREQ,
        CourseField.COREQ,
        CourseField.EXCLUSIONS,
        CourseField.NOTES,
        CourseField.CREDIT_MIN,
        CourseField.CREDIT_MAX,
        CourseField.CREDIT_UNIT,
    )

    academic_year: str = Field(..., pattern=r"^\d{4}/\d{4}$") # e.g. "2026/2027"
    subject: str
    subject_code: str
    course_number: str
    institution: str
    campus: str
    calendar_url: str | None = None
    content_hash: str | None = None
    needs_embedding: bool = True
    title: str | None = None
    description: str | None = None
    prereq: str | None = None
    coreq: str | None = None
    exclusions: str | None = None
    notes: str | None = None
    # Academic Calendar credit weight, e.g. 0.5 / 0.5 / "credits"; a range when min != max.
    credit_min: float | None = None
    credit_max: float | None = None
    credit_unit: str | None = None
    metadata_json: CourseMetadata

    def credit_summary(self) -> dict[str, float | str]:
        """The known credit values keyed min/max/unit (empty when the calendar lists none)."""
        values = {"min": self.credit_min, "max": self.credit_max, "unit": self.credit_unit}
        return {key: value for key, value in values.items() if value is not None}

class CourseCreate(CourseBase):
    pass

class CourseUpdate(FrozenCourse):
    """Strictly typed payload for partial updates."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    campus: str| None = None
    title: str | None = None
    subject: str | None = None
    description: str | None = None
    calendar_url: str | None = None
    prereq: str | None = None
    coreq: str | None = None
    notes: str | None = None
    credit_min: float | None = None
    credit_max: float | None = None
    credit_unit: str | None = None
    exclusions: str | None = None
    content_hash: str | None = None
    needs_embedding: bool | None = None

class CourseRead(CourseBase):
    """view of a course, defaults to reading all values"""
    id: int

class CourseLookupRead(FrozenCourse):
    """view of a course"""
    id: int
    subject: str
    institution: str
    subject_code: str
    course_number: str

class CourseLexicalRead(BaseModel):
    """view for exact match resolution."""
    course_id: str
    course_number: str
    subject: str
    subject_description: str
    title: str
