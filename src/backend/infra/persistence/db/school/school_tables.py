"""SQLAlchemy tables of the school database: courses, course terms (+ meetings, faculty),
WLU pages and scrape pages.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func, text
)
from backend.infra.persistence.db.column_types import JsonDoc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class SchoolBaseTable(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Course(SchoolBaseTable, TimestampMixin):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    academic_year: Mapped[str] = mapped_column(String(16), nullable=False, index=True) # "2026/2027"
    institution: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)  # Anthropology
    subject_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    course_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    campus: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Stable course identity + additional definitions
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)                # Introduction to Anthropology
    calendar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True) # academic-calendar.wlu/course.php?...

    # derived academic-calendar + loris registration data
    description: Mapped[str | None] = mapped_column(Text, nullable=True) # Anthropology is a ... where ... students ... pre-reqs: ...
    prereq: Mapped[str | None] = mapped_column(Text, nullable=True)      # Derived from description or registration
    coreq: Mapped[str | None] = mapped_column(Text, nullable=True)       # Derived from description or registration
    exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)  # Derived from description or registration
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)       # Derived from description extra notes of registration
    # Credit information: 0.5 / 0.5 / "credits"; a range when min != max
    credit_min: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    credit_max: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    credit_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Source + Additional data
    metadata_json: Mapped[dict] = mapped_column(JsonDoc, nullable=False)             # Any additional data that isnt standard

    # Relationship <3
    terms: Mapped[list["CourseTerm"]] = relationship(
        "CourseTerm",
        back_populates="course",
        cascade="all, delete-orphan",
    )

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    needs_embedding: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)

    __table_args__ = (
        UniqueConstraint("academic_year", "institution", "subject_code", "course_number", name="uq_courses_identity"),
    )


class CourseTerm(SchoolBaseTable, TimestampMixin):
    __tablename__ = "course_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id"),
        nullable=False,
        index=True,
    )

    # Registration / offering identity
    term_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)    # 202605
    crn: Mapped[str] = mapped_column(String(32), nullable=False, index=True)          # 332
    term_name: Mapped[str | None] = mapped_column(String(64), nullable=True)          # Spring 2026

    # Course Info
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)  # Anthropology
    subject_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    course_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Delivery / section summary
    section_code: Mapped[str | None] = mapped_column(String(32), nullable=True)       # VA1 / L1 / etc.
    part_of_term: Mapped[str | None] = mapped_column(String(32), nullable=True)       # 1 = full term, 2 = first half, ...
    schedule_type: Mapped[str | None] = mapped_column(String(128), nullable=True)        # Type of class: Lecture / Lab / Tutorial / Seminar
    open_section: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    instructional_method: Mapped[str | None] = mapped_column(String(128), nullable=True) # How it is delivered: Online / In Person / Off-Campus / Field Supervision

    # LORIS data may differ from academic calendar
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prereq: Mapped[str | None] = mapped_column(Text, nullable=True)
    coreq: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    restrictions: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Credit (one value per section)
    credit_hours: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    credit_hour_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    credit_hour_high: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Enrollment snapshot (one value per section)
    maximum_enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enrollment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seats_available: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wait_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wait_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wait_available: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Child collections, one row per item keyed by this section (as LORIS keys them by CRN).
    # lazy="raise": loaded only when a view asks for them (apply_view adds selectinload).
    meetings: Mapped[list["CourseTermMeeting"]] = relationship(
        back_populates="course_term",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CourseTermMeeting.position",
        lazy="raise",
    )
    faculty: Mapped[list["CourseTermFaculty"]] = relationship(
        back_populates="course_term",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CourseTermFaculty.position",
        lazy="raise",
    )

    # Optional source fidelity / extra payload
    metadata_json: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)

    # Relationship <3
    course: Mapped["Course"] = relationship("Course", back_populates="terms")

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    needs_embedding: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)

    __table_args__ = (
        UniqueConstraint("term_code", "crn", name="uq_course_terms_term_crn"),
    )

class CourseTermChildMixin:
    """A row of an ordered child collection of a CourseTerm, replaced as a whole on upsert."""
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_term_id: Mapped[int] = mapped_column(
        ForeignKey("course_terms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # Order within the section, as LORIS lists it


# Attribute names are the domain (LORIS) field names; the columns are snake_case.
class CourseTermMeeting(SchoolBaseTable, CourseTermChildMixin):
    __tablename__ = "course_term_meetings"

    beginTime: Mapped[str | None] = mapped_column("begin_time", String(8), nullable=True)   # "1000"
    endTime: Mapped[str | None] = mapped_column("end_time", String(8), nullable=True)
    building: Mapped[str | None] = mapped_column(String(128), nullable=True)
    room: Mapped[str | None] = mapped_column(String(128), nullable=True)
    monday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tuesday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wednesday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    thursday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    friday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    saturday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sunday: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    startDate: Mapped[str | None] = mapped_column("start_date", String(32), nullable=True)
    endDate: Mapped[str | None] = mapped_column("end_date", String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scheduleType: Mapped[str | None] = mapped_column("schedule_type", String(128), nullable=True)

    course_term: Mapped["CourseTerm"] = relationship(back_populates="meetings")

    __table_args__ = (
        Index("ix_course_term_meetings_building_room", "building", "room"),
    )


class CourseTermFaculty(SchoolBaseTable, CourseTermChildMixin):
    __tablename__ = "course_term_faculty"

    bannerId: Mapped[str | None] = mapped_column("banner_id", String(32), nullable=True, index=True)
    displayName: Mapped[str | None] = mapped_column("display_name", String(255), nullable=True)
    emailAddress: Mapped[str | None] = mapped_column("email_address", String(255), nullable=True)
    primaryIndicator: Mapped[bool | None] = mapped_column("primary_indicator", Boolean, nullable=True)

    course_term: Mapped["CourseTerm"] = relationship(back_populates="faculty")


# General info like departments, glossary defintiions, wlu website data
class WluPage(SchoolBaseTable, TimestampMixin):
    __tablename__ = "wlu_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    site_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # academic_calendar / wlu / students_wlu

    record_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # faculty / department / program / glossary / page (AcademicCalendarType)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    metadata_json: Mapped[dict] = mapped_column(JsonDoc, nullable=False)

    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    needs_embedding: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)

    __table_args__ = (
        UniqueConstraint("version", "url", name="uq_wlu_pages_identity"),
    )

class SchoolScrapePageTable(SchoolBaseTable):
    __tablename__ = "scrape_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    site_name: Mapped[str] = mapped_column(String(120), index=True)
    parent_url: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    blob_key: Mapped[str | None] = mapped_column(Text, nullable=True )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    etag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_modified_header: Mapped[str | None] = mapped_column(String(128), nullable=True)
    needs_persistence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        index=True,
    )

    metadata_json: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)

    __table_args__ = (
        UniqueConstraint("url", "version", name="uq_scrape_pages_url_version"),
    )
