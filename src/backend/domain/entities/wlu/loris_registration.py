"""LORIS term offerings (CourseTerm): sections, meetings, rooms, instructors and their metadata.

A CourseTerm is a term-specific offering of a Course and may differ from the calendar entry.
"""
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field


class FrozenRegistration(BaseModel):
    model_config = ConfigDict(frozen=True)


class CourseTermField(StrEnum):
    ID = "id"
    COURSE_ID = "course_id"
    TERM_CODE = "term_code"
    CRN = "crn"
    TITLE = "title"
    SUBJECT = "subject"
    SUBJECT_CODE = "subject_code"
    COURSE_NUMBER = "course_number"
    TERM_NAME = "term_name"
    SECTION_CODE = "section_code"
    PART_OF_TERM = "part_of_term"
    SCHEDULE_TYPE = "schedule_type"
    OPEN_SECTION = "open_section"
    INSTRUCTIONAL_METHOD = "instructional_method"
    DESCRIPTION = "description"
    PREREQ = "prereq"
    COREQ = "coreq"
    EXCLUSIONS = "exclusions"
    NOTES = "notes"
    RESTRICTIONS = "restrictions"
    CREDIT_HOURS = "credit_hours"
    CREDIT_HOUR_LOW = "credit_hour_low"
    CREDIT_HOUR_HIGH = "credit_hour_high"
    MAXIMUM_ENROLLMENT = "maximum_enrollment"
    ENROLLMENT = "enrollment"
    SEATS_AVAILABLE = "seats_available"
    WAIT_CAPACITY = "wait_capacity"
    WAIT_COUNT = "wait_count"
    WAIT_AVAILABLE = "wait_available"
    MEETINGS = "meetings"
    FACULTY = "faculty"
    METADATA_JSON = "metadata_json"
    CONTENT_HASH = "content_hash"
    NEEDS_EMBEDDING = "needs_embedding"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class LexiconEntityType(StrEnum):
    SUBJECT = "subject"
    PROGRAM = "program"
    DEPARTMENT = "department"
    FACULTY = "faculty"
    REGISTRATION_NOTES = "registration_notes"

class CourseFaculty(FrozenRegistration):
    """One instructor of a section, as LORIS lists it (a row per section, keyed by its CRN)."""
    # Banner's stable person id; the identity used to de-duplicate instructors across lists.
    bannerId: str | None = None
    displayName: str | None = None
    emailAddress: str | None = None
    primaryIndicator: bool | None = None

class MeetingRoom(FrozenRegistration):
    """A physical meeting location exactly as LORIS stores it. The room alone is not an identity:
    LORIS reuses names across buildings ("GYM" in US and AC), so (building, room) is."""
    building: str | None = None
    room: str

class CourseMeetingTime(FrozenRegistration):
    """One scheduled meeting of a section. Day flags are flat, as in LORIS's meetingTime object.
    Instructors live on the section (CourseTermBase.faculty), which already merges per-meeting lists."""
    beginTime: str | None = None
    endTime: str | None = None
    building: str | None = None
    room: str | None = None
    monday: bool | None = None
    tuesday: bool | None = None
    wednesday: bool | None = None
    thursday: bool | None = None
    friday: bool | None = None
    saturday: bool | None = None
    sunday: bool | None = None
    startDate: str | None = None
    endDate: str | None = None
    category: str | None = None
    scheduleType: str | None = None

class CourseTermMetadata(FrozenRegistration):
    campusDescription: str | None = None
    instructionalMethod: str | None = None

class CourseTermBase(FrozenRegistration):
    IDENTITY_FIELDS: ClassVar[tuple[CourseTermField, ...]] = (
        CourseTermField.TERM_CODE,
        CourseTermField.CRN,
    )

    EMBED_FIELDS: ClassVar[tuple[CourseTermField, ...]] = (
        CourseTermField.SUBJECT_CODE,
        CourseTermField.COURSE_NUMBER,
        CourseTermField.TITLE,
        CourseTermField.SUBJECT,
        CourseTermField.TERM_CODE,
        CourseTermField.TERM_NAME,
        CourseTermField.SECTION_CODE,
        CourseTermField.CRN,
        CourseTermField.DESCRIPTION,
        CourseTermField.PREREQ,
        CourseTermField.COREQ,
        CourseTermField.EXCLUSIONS,
        CourseTermField.RESTRICTIONS,
        CourseTermField.NOTES,
        CourseTermField.INSTRUCTIONAL_METHOD,
    )

    course_id: int
    term_code: str = Field(..., pattern=r"^\d{4}(01|05|09)$")
    term_name: str | None = None
    crn: str
    subject_code: str
    course_number: str
    title: str | None = None
    subject: str
    section_code: str | None = None
    part_of_term: str | None = None
    schedule_type: str | None = None
    open_section: bool | None = None
    instructional_method: str | None = None
    description: str | None = None
    prereq: str | None = None
    coreq: str | None = None
    exclusions: str | None = None
    notes: str | None = None
    restrictions: str | None = None
    needs_embedding: bool = True
    # Credit and seat counts: one value each per section, so plain filterable columns.
    credit_hours: float | None = None
    credit_hour_low: float | None = None
    credit_hour_high: float | None = None
    maximum_enrollment: int | None = None
    enrollment: int | None = None
    seats_available: int | None = None
    wait_capacity: int | None = None
    wait_count: int | None = None
    wait_available: int | None = None
    # Child collections of the section, stored as their own rows and replaced as a whole on upsert.
    meetings: list[CourseMeetingTime] = Field(default_factory=list)
    faculty: list[CourseFaculty] = Field(default_factory=list)
    metadata_json: CourseTermMetadata | None = None

class CourseTermCreate(CourseTermBase):
    pass

class CourseTermUpdate(FrozenRegistration):
    term_name: str | None = None
    title: str | None = None
    subject: str | None = None
    subject_code: str | None = None
    course_number: str | None = None
    section_code: str | None = None
    part_of_term: str | None = None
    schedule_type: str | None = None
    open_section: bool | None = None
    instructional_method: str | None = None
    description: str | None = None
    prereq: str | None = None
    coreq: str | None = None
    exclusions: str | None = None
    notes: str | None = None
    restrictions: str | None = None
    needs_embedding: bool | None = None
    credit_hours: float | None = None
    credit_hour_low: float | None = None
    credit_hour_high: float | None = None
    maximum_enrollment: int | None = None
    enrollment: int | None = None
    seats_available: int | None = None
    wait_capacity: int | None = None
    wait_count: int | None = None
    wait_available: int | None = None
    # Set (even to []) to replace the section's collection; left unset to keep it.
    meetings: list[CourseMeetingTime] | None = None
    faculty: list[CourseFaculty] | None = None
    metadata_json: CourseTermMetadata | None = None

class CourseTermRead(CourseTermBase):
    id: int



class RegistrationDescription(FrozenRegistration):
    description: str | None = None
    prereq: str | None = None
    coreq: str | None = None
    exclusions: str | None = None
    notes: str | None = None
    SEPARATOR: ClassVar[str]= "\n---LORIS_MENU---\n" # For merging desc and menu pre-reqs