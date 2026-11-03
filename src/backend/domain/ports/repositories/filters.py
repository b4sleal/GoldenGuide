"""Typed query filters for every repository (no raw SQL or ORM types cross this boundary)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.entities.conversations import MessageStatus
from backend.domain.entities.jobs import JobBatchStatus, JobStatus
from backend.domain.entities.scraping import ScrapeStatus
from backend.domain.entities.wlu.academic_level import AcademicLevel
from backend.domain.entities.wlu.loris_registration import MeetingRoom
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType


class DocumentFilter(BaseModel):
    model_config = ConfigDict(frozen=True)
    active: bool | None = Field(default=None)
    source_type: str | None = Field(default=None)
    document_ids: list[str] | None = Field(default=None)

class JobRunFilter(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int | None = None
    job_name: str | None = None
    statuses: tuple[JobStatus, ...] | None = None

class JobBatchFilter(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: int | None = None
    batch_no: int | None = None
    status: JobBatchStatus | None = None
    statuses: tuple[JobBatchStatus, ...] | None = None

class ConversationFilter(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID | None = None
    owner_subject: str | None = None
    client_id_hash: str | None = None
    # Last activity before this time: conversations past the retention period.
    updated_before: datetime | None = None

    def is_empty(self) -> bool:
        return all(value is None for value in self.model_dump().values())

class ChatMessageFilter(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int | None = None
    conversation_id: UUID | None = None
    statuses: tuple[MessageStatus, ...] | None = None

class CourseFilter(BaseModel):
    """Pure domain DTO for filtering courses. Contains ZERO translation logic."""
    model_config = ConfigDict(frozen=True)

    # Exact matches
    academic_year: str | None = Field(default=None, description="e.g., 2024, 2025")
    institution: str | None = Field(default=None, description="e.g., WLU, UW")
    campus: str | None = Field(default=None, description="e.g., Waterloo, Brantford, Milton")
    subject: str | None = Field(default=None, description="e.g., Computer Science, Mathematics, Business")
    subject_code: str | None = Field(default=None, description="e.g., CP, MA, BU")
    course_number: str | None = Field(default=None, description="e.g., 317, 104")

    # Partial matches
    title_contains: str | None = Field(default=None, description="Partial match on course title")
    specific_course_codes: set[tuple[str, str, str]] | None = Field(
        default=None,
        description="Set of (subject_code, course_number, institution) tuples for bulk ELT lookups. e.g., {('CP', '104', 'WLU'), ('MA', '317', 'UW')}"
    )

    has_prereqs: bool | None = Field(default=None, description="Checks if prereq field is populated")
    has_exclusions: bool | None = Field(default=None, description="Checks if exclusions field is populated")
    needs_embedding: bool | None = Field(default=None, description="Fetches dirty rows")
    prerequisite_of: str | None = None
    corequisite_of: str | None = None
    excludes_course: str | None = None

    levels: list[int] | None = None  # Course-number year levels (100, 200, ...), not AcademicLevel.
    academic_level: AcademicLevel | None = Field(
        default=None, description="Courses of this level, plus courses with no level (LORIS-only)",
    )

class WluPageFilter(BaseModel):
    """Pure domain DTO for filtering academic records."""
    model_config = ConfigDict(frozen=True)

    site_name: str | None = Field(default=None, description="e.g., academic_calendar_wlu")
    record_ids: list[int] | None = Field(default=None, description="Exact records (an IN clause).")

    # Allows querying a single type OR multiple types
    record_type: AcademicCalendarType | None = Field(default=None, description="e.g., glossary, page")
    record_types: list[AcademicCalendarType] | None = Field(default=None, description="Generates an IN clause")
    academic_level: AcademicLevel | None = Field(
        default=None, description="Pages of this level, plus pages that are not level-specific (NULL)",
    )

    # Partial matches
    title_contains: str | None = Field(default=None)
    title_terms: list[str] | None = None  # Canonical entity names, never raw SQL.
    title_operator: Literal["all", "any"] = "all"
    url_contains: str | None = Field(default=None)

    # State checks
    has_content: bool | None = Field(default=None, description="Checks if text body was successfully extracted")
    needs_embedding: bool | None = Field(default=None, description="Fetches dirty rows")

class CourseTermFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    term_code: str | None = None
    course_id: int | None = None
    subject_code: str | None = None
    course_number: str | None = None

    levels: list[int] | None = None
    credit: list[float] | None = None
    campuses: list[str] | None = None
    deliveries: list[str] | None = None
    sub_terms: list[str] | None = None
    schedule_types: list[str] | None = None

    day_preference: list[str] | None = None
    day_exclusion: list[str] | None = None
    rooms: list[MeetingRoom] | None = None  # Any meeting in one of these rooms.
    instructor_ids: list[str] | None = None  # Banner ids; any one of them teaches the section.

    open_section: bool | None = None
    has_seats: bool | None = None
    has_waitlist: bool | None = None

    instructional_method: str | None = None
    schedule_type: str | None = None
    needs_embedding: bool | None = None

class ScrapePageFilter(BaseModel):
    """Pure domain DTO for filtering scrape jobs."""
    model_config = ConfigDict(frozen=True)

    site_name: str | None = Field(default=None)
    version: str | None = Field(default=None, description="Filters by the generic snapshot version")
    # State matches
    status: ScrapeStatus | None = Field(default=None)
    statuses: list[ScrapeStatus] | None = Field(default=None)

    # Conditionals
    has_blob: bool | None = Field(default=None, description="Requires blob_key to be present")

    # ETL Specifics
    is_unmapped: bool | None = Field(default=None, description="Filters for pages not yet parsed into Course/Academic tables")



