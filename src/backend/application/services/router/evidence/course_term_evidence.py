"""LORIS term sections -> Evidence (prompt text at three detail levels, plus a table row). Pure functions."""
import json
from collections import defaultdict

from backend.application.services.router.evidence.fields import field_lines
from backend.domain.entities.retrieval import Evidence, TableRow
from backend.domain.entities.wlu.academic_calendar import Weekday
from backend.domain.entities.wlu.loris_registration import (
    CourseMeetingTime,
    CourseTermField,
    CourseTermRead,
)

# Text fields usually identical across a course's sections in one term: printed once per group.
SHARED_FIELDS = {
    CourseTermField.DESCRIPTION: "Description",
    CourseTermField.PREREQ: "Prerequisites",
    CourseTermField.COREQ: "Corequisites",
    CourseTermField.EXCLUSIONS: "Exclusions",
}
EMPTY = "—"
RECORD = "LORIS section record"


def meeting_days(meeting: CourseMeetingTime) -> str:
    """'Mon/Wed' from LORIS day flags; '—' when no days are recorded (e.g. online asynchronous)."""
    names = [day.value[:3].title() for day in Weekday if getattr(meeting, day.value)]
    return "/".join(names) or EMPTY


def clock(value: str | None) -> str | None:
    """LORIS times are 'HHMM' strings ('1000' -> '10:00')."""
    if not value or len(value) != 4 or not value.isdigit():
        return None
    return f"{value[:2]}:{value[2:]}"


def meeting_time(meeting: CourseMeetingTime) -> str:
    """'10:00–11:20', the start time alone, or '—'."""
    begin, end = clock(meeting.beginTime), clock(meeting.endTime)
    if begin and end:
        return f"{begin}–{end}"
    return begin or EMPTY


def meeting_location(meeting: CourseMeetingTime) -> str:
    return " ".join(part for part in (meeting.building, meeting.room) if part) or EMPTY


def join_lines(values) -> str:
    """One line per meeting, so a section meeting twice a week stays readable in one cell."""
    return "\n".join(values) or EMPTY


def registration_status(term: CourseTermRead) -> str:
    """Open / Closed from LORIS; 'Unknown' when LORIS did not say (never guessed as open)."""
    if term.open_section is True:
        return "Open"
    if term.open_section is False:
        return "Closed"
    return "Unknown"


def section_evidence(
        term: CourseTermRead,
        primary: bool,
        registration_url: str,
        shared: dict[CourseTermField, str] | None = None,
        first_in_group: bool = True,
) -> Evidence:
    """Evidence for one section. `shared` text is printed only on the group's first section."""
    code = f"{term.subject_code}{term.course_number}"
    shared = shared or {}
    seats = term.seats_available
    waitlist = term.wait_available
    status = registration_status(term)
    meetings = json.dumps([meeting.model_dump(mode="json") for meeting in term.meetings], separators=(",", ":"))

    # "TBA" = not yet assigned in LORIS; the model must not read it as "no instructor".
    names = ", ".join(faculty.displayName for faculty in term.faculty if faculty.displayName)
    instructors = names or "TBA (not yet assigned)"

    # Shared text is printed once, on the group's first section; other sections leave it out entirely.
    present, absent = field_lines({
        "Title": term.title,
        "Restrictions": term.restrictions,
        **{label: getattr(term, field.value) for field, label in SHARED_FIELDS.items() if field not in shared},
    }, RECORD)
    content = [
        f"Course: {code}",
        f"Term: {term.term_name or term.term_code}",
        f"Term code: {term.term_code}",
        f"Section: {term.section_code or 'Unknown'}",
        f"CRN: {term.crn}",
        f"Instructor: {instructors}",
        f"Registration status: {status}",
        f"Seats available: {seats if seats is not None else 'Unknown'}",
        f"Waitlist spaces: {waitlist if waitlist is not None else 'Unknown'}",
        f"Instructional method: {term.instructional_method or 'Unknown'}",
        f"Schedule type: {term.schedule_type or 'Unknown'}",
        f"Meetings: {meetings}",
        *present,
    ]
    for field, label in SHARED_FIELDS.items():
        if field in shared and first_in_group:
            content.append(f"{label} (shared across retrieved sections of this course/term): {shared[field]}")
    content += absent

    present, absent = field_lines({"Title": term.title, "Restrictions": term.restrictions}, RECORD)
    compact_content = "\n".join([
        f"Course: {code}",
        f"Term: {term.term_name or term.term_code}",
        f"Term code: {term.term_code}",
        f"Section: {term.section_code or 'Unknown'}",
        f"CRN: {term.crn}",
        f"Instructor: {instructors}",
        f"Registration status: {status}",
        f"Seats available: {seats if seats is not None else 'Unknown'}",
        *present,
        *absent,
    ])

    present, absent = field_lines({"Title": term.title}, RECORD)
    minimal_content = "\n".join([
        f"Course: {code}",
        f"Term: {term.term_name or term.term_code}",
        f"Section: {term.section_code or 'Unknown'}",
        f"CRN: {term.crn}",
        f"Registration status: {status}",
        *present,
        *absent,
    ])

    # Tabular view of this section. All sections of one course in one term share a group, so the
    # answer can show them as a single table built from these exact values (see evidence_tables.py).
    table_row = TableRow(
        group=f"{code} sections — {term.term_name or term.term_code}",
        cells={
            "Section": term.section_code or EMPTY,
            "Type": term.schedule_type or EMPTY,
            "Days": join_lines(meeting_days(meeting) for meeting in term.meetings),
            "Time": join_lines(meeting_time(meeting) for meeting in term.meetings),
            "Location": join_lines(meeting_location(meeting) for meeting in term.meetings),
            # Primary instructor first (merge_faculty sorts it). No instructor means LORIS lists
            # the section as "TBA" (not yet assigned), which is different from unknown.
            "Instructor": names or "TBA",
            "Status": status,
            "Seats": str(seats) if seats is not None else EMPTY,
            "Waitlist": str(waitlist) if waitlist is not None else EMPTY,
            "CRN": term.crn,
        },
    )

    # What the answer model reads when this section is shown in that table: one line, enough to
    # summarize and recommend, too little to retype as a listing. Shared course text stays on the first.
    schedule = ", ".join(
        f"{meeting_days(meeting)} {meeting_time(meeting)}" for meeting in term.meetings
    ) or "No scheduled meetings"
    table_content = [(
        f"Course: {code} | Term: {term.term_name or term.term_code} | Section: {term.section_code or 'Unknown'} "
        f"({term.schedule_type or 'Unknown'}) | {schedule} | {term.instructional_method or 'Unknown'} | "
        f"Instructor: {instructors} | {status}, seats: {seats if seats is not None else 'Unknown'}"
    )]
    if term.restrictions:
        table_content.append(f"Restrictions: {term.restrictions}")
    for field, label in SHARED_FIELDS.items():
        if field in shared and first_in_group:
            table_content.append(f"{label} (shared across retrieved sections of this course/term): {shared[field]}")

    return Evidence(
        table_row=table_row,
        table_content="\n".join(table_content),
        source_id=f"course_term:{term.id}",
        title=f"{code} — {term.term_name or term.term_code} — {term.section_code or term.crn}",
        # LORIS has no per-section page, so every section cites the registration entry point.
        url=registration_url,
        content="\n".join(content),
        compact_content=compact_content,
        minimal_content=minimal_content,
        primary=primary,
    )


def course_term_evidence(terms: list[CourseTermRead], primary: bool, registration_url: str) -> list[Evidence]:
    """One Evidence per section, with text shared by every section of a course/term printed once."""
    groups: dict[tuple[str, str, str], list[CourseTermRead]] = defaultdict(list)
    for term in terms:
        groups[(term.subject_code, term.course_number, term.term_code)].append(term)

    evidence = []
    for group in groups.values():
        shared = {}
        for field in SHARED_FIELDS:
            values = [getattr(term, field.value) for term in group]
            if len(group) > 1 and values[0] and all(value == values[0] for value in values):
                shared[field] = values[0]

        evidence += [
            section_evidence(term, primary, registration_url, shared, first_in_group=index == 0)
            for index, term in enumerate(group)
        ]
    return evidence
