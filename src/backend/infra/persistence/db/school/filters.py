"""Translate school filter models into SQLAlchemy WHERE clauses."""
import re

from sqlalchemy import and_, or_
from backend.domain.ports.repositories.filters import CourseFilter, WluPageFilter, ScrapePageFilter, \
    CourseTermFilter
from sqlalchemy import Select, tuple_, or_

from backend.domain.entities.wlu.academic_calendar import Weekday
from backend.domain.entities.wlu.academic_level import AcademicLevel
from backend.domain.entities.wlu.loris_registration import MeetingRoom
from backend.infra.persistence.db.school.school_tables import (
    Course,
    CourseTerm,
    CourseTermFaculty,
    CourseTermMeeting,
    SchoolScrapePageTable,
    WluPage,
)

def course_reference_pattern(code: str) -> str:
    match = re.fullmatch(r"([A-Z]{2})(\d{3}[A-Z]?)", code.upper())

    if not match:
        raise ValueError(f"Invalid course code: {code}")

    subject, number = match.groups()

    return (
        rf"(^|[^[:alnum:]])"
        rf"{subject}[[:space:]]*{number}"
        rf"([^[:alnum:]]|$)"
    )

def for_level(column, level: AcademicLevel):
    """Rows of `level`, plus rows without one: those apply to every student (tuition, dates)."""
    return or_(column == level.value, column.is_(None))


class CourseFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: CourseFilter | None) -> Select:
        if not filters: return stmt

        if filters.course_number is not None:
            stmt = stmt.where(Course.course_number == filters.course_number)

        if filters.title_contains is not None:
            stmt = stmt.where(Course.title.ilike(f"%{filters.title_contains}%"))

        if filters.has_prereqs is True:
            stmt = stmt.where(Course.prereq.is_not(None))
        elif filters.has_prereqs is False:
            stmt = stmt.where(Course.prereq.is_(None))

        if filters.has_exclusions is True:
            stmt = stmt.where(Course.exclusions.is_not(None))
        elif filters.has_exclusions is False:
            stmt = stmt.where(Course.exclusions.is_(None))

        if filters.needs_embedding is True:
            stmt = stmt.where(
                Course.needs_embedding.is_(filters.needs_embedding)
            )
        if filters.specific_course_codes:
            stmt = stmt.where(
                tuple_(
                    Course.subject_code,
                    Course.course_number,
                    Course.institution,
                ).in_(filters.specific_course_codes)
            )

        if filters.institution is not None:
            stmt = stmt.where(Course.institution == filters.institution)

        if filters.academic_year is not None:
            stmt = stmt.where(Course.academic_year == filters.academic_year)

        if filters.campus is not None:
            stmt = stmt.where(Course.campus == filters.campus)

        if filters.subject_code is not None:
            stmt = stmt.where(Course.subject_code == filters.subject_code)

        if filters.subject is not None:
            stmt = stmt.where(Course.subject == filters.subject)

        if filters.prerequisite_of:
            pattern = course_reference_pattern(filters.prerequisite_of)
            stmt = stmt.where(Course.prereq.op("~*")(pattern))

        if filters.corequisite_of:
            pattern = course_reference_pattern(filters.corequisite_of)
            stmt = stmt.where(Course.coreq.op("~*")(pattern))

        if filters.excludes_course:
            pattern = course_reference_pattern(filters.excludes_course)
            stmt = stmt.where(Course.exclusions.op("~*")(pattern))

        if filters.levels:
            stmt = stmt.where(
                or_(*[
                    Course.course_number.like(f"{level // 100}%")
                    for level in filters.levels
                ])
            )

        if filters.academic_level is not None:
            stmt = stmt.where(for_level(Course.academic_level, filters.academic_level))

        return stmt



class WluPageFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: WluPageFilter | None) -> Select:
        if not filters: return stmt

        if filters.needs_embedding is not None:
            stmt = stmt.where(
                WluPage.needs_embedding.is_(filters.needs_embedding)
            )

        if filters.site_name is not None:
            stmt = stmt.where(WluPage.site_name == filters.site_name)

        if filters.record_ids is not None:
            stmt = stmt.where(WluPage.id.in_(filters.record_ids))

        if filters.record_type is not None:
            stmt = stmt.where(WluPage.record_type == filters.record_type.value)

        if filters.record_types is not None:
            stmt = stmt.where(WluPage.record_type.in_([rt.value for rt in filters.record_types]))

        if filters.academic_level is not None:
            stmt = stmt.where(for_level(WluPage.academic_level, filters.academic_level))

        if filters.title_contains is not None:
            stmt = stmt.where(WluPage.title.ilike(f"%{filters.title_contains}%"))

        if filters.title_terms:
            # SQLAlchemy binds/escapes all terms. No string-built SQL.
            predicates = [
                WluPage.title.icontains(term, autoescape=True)
                for term in filters.title_terms
            ]
            stmt = stmt.where(
                and_(*predicates) if filters.title_operator == "all"
                else or_(*predicates)
            )

        if filters.url_contains is not None:
            stmt = stmt.where(WluPage.url.ilike(f"%{filters.url_contains}%"))

        if filters.has_content is True:
            stmt = stmt.where(WluPage.content.is_not(None))
        elif filters.has_content is False:
            stmt = stmt.where(WluPage.content.is_(None))

        return stmt

from sqlalchemy import Select, exists, literal, select

class ScrapePageFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: ScrapePageFilter | None, mapped_urls_subquery=None) -> Select:
        if not filters:
            return stmt

        if filters.site_name:
            stmt = stmt.where(SchoolScrapePageTable.site_name == filters.site_name)

        if filters.status:
            stmt = stmt.where(SchoolScrapePageTable.status == filters.status.value)

        if filters.statuses:
            stmt = stmt.where(SchoolScrapePageTable.status.in_([s.value for s in filters.statuses])) # <-- Extract values

        if filters.has_blob is True:
            stmt = stmt.where(SchoolScrapePageTable.blob_key.is_not(None))
        elif filters.has_blob is False:
            stmt = stmt.where(SchoolScrapePageTable.blob_key.is_(None))

        # Handle the complex cross-table subquery cleanly with direct ORM references
        if filters.is_unmapped is True and mapped_urls_subquery is not None:
            stmt = stmt.where(
                ~exists(
                    select(literal(1))
                    .select_from(mapped_urls_subquery)
                    .where(mapped_urls_subquery.c.url == SchoolScrapePageTable.url)
                )
            )

        if filters.version:
            stmt = stmt.where(SchoolScrapePageTable.version == filters.version)

        return stmt

def in_room(room: MeetingRoom):
    """Exact (building, room) match on one meeting, the identity LORIS stores."""
    building = CourseTermMeeting.building
    return and_(
        CourseTermMeeting.room == room.room,
        building.is_(None) if room.building is None else building == room.building,
    )


def occurs_on(day: str):
    return getattr(CourseTermMeeting, Weekday(day).value).is_(True)


class CourseTermFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: CourseTermFilter | None) -> Select:
        if not filters:
            return stmt

        if filters.term_code is not None:
            stmt = stmt.where(CourseTerm.term_code == filters.term_code)

        if filters.needs_embedding is not None:
            stmt = stmt.where(
                CourseTerm.needs_embedding == filters.needs_embedding
            )

        if filters.course_id is not None:
            stmt = stmt.where(CourseTerm.course_id == filters.course_id)

        if filters.subject_code is not None:
            stmt = stmt.where(CourseTerm.subject_code == filters.subject_code)

        if filters.course_number is not None:
            stmt = stmt.where(CourseTerm.course_number == filters.course_number)

        if filters.open_section is not None:
            stmt = stmt.where(CourseTerm.open_section == filters.open_section)

        if filters.has_seats is not None:
            seats = CourseTerm.seats_available

            if filters.has_seats:
                stmt = stmt.where(seats > 0)
            else:
                stmt = stmt.where(seats <= 0)

        if filters.has_waitlist is not None:
            waitlist = CourseTerm.wait_available

            if filters.has_waitlist:
                stmt = stmt.where(waitlist > 0)
            else:
                stmt = stmt.where(waitlist <= 0)

        if filters.instructional_method is not None:
            stmt = stmt.where(
                CourseTerm.instructional_method == filters.instructional_method
            )

        if filters.schedule_type is not None:
            stmt = stmt.where(CourseTerm.schedule_type == filters.schedule_type)

        if filters.levels:
            stmt = stmt.where(or_(*[
                CourseTerm.course_number.like(f"{level // 100}%")
                for level in filters.levels
            ]))

        if filters.credit:
            stmt = stmt.where(CourseTerm.credit_hours.in_(filters.credit))

        if filters.schedule_types:
            stmt = stmt.where(
                CourseTerm.schedule_type.in_(filters.schedule_types)
            )

        if filters.instructor_ids:
            # The section lists an instructor with one of these bannerIds.
            stmt = stmt.where(CourseTerm.faculty.any(CourseTermFaculty.bannerId.in_(filters.instructor_ids)))

        if filters.day_preference or filters.day_exclusion or filters.rooms:
            # A section without meetings has no known schedule: never a match, not "conflict-free".
            stmt = stmt.where(CourseTerm.meetings.any())

            # Room and preferred days must hold for the SAME meeting (a room on Friday),
            # not a Monday meeting in that room plus a Friday meeting elsewhere.
            same_meeting = []

            if filters.rooms:
                same_meeting.append(or_(*[in_room(room) for room in filters.rooms]))

            if filters.day_preference:
                same_meeting.append(or_(*[
                    occurs_on(day) for day in filters.day_preference
                ]))  # At least one preferred day.

            if same_meeting:
                stmt = stmt.where(CourseTerm.meetings.any(and_(*same_meeting)))

            if filters.day_exclusion:
                stmt = stmt.where(and_(*[
                    ~CourseTerm.meetings.any(occurs_on(day)) for day in filters.day_exclusion
                ]))  # No excluded-day meetings.


        return stmt

