"""LORIS JSON/HTML -> course and course-term payloads: requirements, meetings, instructors. Pure functions."""
import html
from typing import Any
import re

from bs4 import BeautifulSoup

from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.loris_registration import RegistrationDescription, LexiconEntityType
from backend.domain.entities.wlu.course import CourseCreate
from backend.domain.entities.wlu.academic_calendar import Weekday
from backend.domain.entities.wlu.loris_registration import (
    CourseTermCreate, CourseMeetingTime, CourseFaculty, CourseTermMetadata,
)
from backend.application.use_cases.scraping.common_parsing import clean_text_value

def term_code_to_academic_year(term_code: str) -> str:
    year = int(term_code[:4])
    if term_code[4:] == "09":
        return f"{year}/{year + 1}"
    return f"{year - 1}/{year}"

def combine_requirements(
        description: str | None,
        menu: str | None,
) -> str | None:
    if not description and not menu:
        return None
    # Prerequisites and corequisites exist in description and in LORIS menu
    # Combine them with a separator to preserve both sources of information
    return f"{description or ''}{RegistrationDescription.SEPARATOR}{menu or ''}"

def parse_registration_description(
        text: str | None,
        lexicon_resolver: WluLexiconResolver,
        menu_prereq: str | None = None,
        menu_coreq: str | None = None
) -> RegistrationDescription:
    if not text:
        return RegistrationDescription(
            prereq=combine_requirements(None, menu_prereq),
            coreq=combine_requirements(None, menu_coreq),
        )

    aliases = lexicon_resolver.get_aliases(
        LexiconEntityType.REGISTRATION_NOTES
    )

    canonical_fields = {
        entry.canonical.casefold(): key
        for key, entry in
        lexicon_resolver.lexicon_profile.registration_notes.items()
    }

    pattern = re.compile(
        r"(?<![\w-])("
        + "|".join(
            re.escape(alias)
            for alias in sorted(aliases, key=len, reverse=True)
        )
        + r")\s*:",
        re.IGNORECASE,
        )

    matches = list(pattern.finditer(text))

    if not matches:
        return RegistrationDescription(
            description=text.strip() or None,
            prereq=combine_requirements(None, menu_prereq),
            coreq=combine_requirements(None, menu_coreq),
        )

    description = text[:matches[0].start()].strip() or None

    fields = {
        "prereq": [],
        "coreq": [],
        "exclusions": [],
        "notes": [],
    }

    for index, match in enumerate(matches):
        canonical = lexicon_resolver.resolve_registration_header(match.group(1))
        if not canonical:
            continue

        header_key = canonical_fields[canonical.casefold()]

        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        value = text[match.end():end].strip()

        if not value:
            continue

        match header_key:
            case "prerequisites":
                fields["prereq"].append(value)

            case "corequisites":
                fields["coreq"].append(value)

            case "exclusions":
                fields["exclusions"].append(value)

            case _:
                fields["notes"].append(f"{canonical}: {value}")

    def combine(values: list[str]) -> str | None:
        return "\n".join(values) or None

    return RegistrationDescription(
        description=description,
        prereq=combine_requirements(
            combine(fields["prereq"]),
            menu_prereq,
        ),
        coreq=combine_requirements(
            combine(fields["coreq"]),
            menu_coreq,
        ),
        exclusions=combine(fields["exclusions"]),
        notes=combine(fields["notes"]),
    )

def parse_institution(campus_description: str | None) -> str:
    if campus_description == "University of Waterloo":
        return "UW"
    else:
        return "WLU"

def combine_registration_requirements(
        description_text: str | None,
        menu_text: str | None,
        name: str,
) -> str: # For pre-req co-req
    missing = "No information available."

    return (
        f"Description {name}:\n{description_text or missing}\n\n"
        f"Menu {name}:\n{menu_text or missing}"
    )

def parse_requirement_table(
        raw_html: str | None,
        lexicon_resolver: WluLexiconResolver,
) -> str | None:
    if not raw_html:
        return None

    soup = BeautifulSoup(html.unescape(raw_html), "html.parser")
    lines = []
    depth = 0

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [
                cell.get_text(" ", strip=True)
                for cell in tr.find_all(["th", "td"], recursive=False)
            ]

            # LORIS columns:
            # And/Or, (, Test, Score, Subject, Number, Level, Grade, )
            if len(cells) < 9:
                continue

            operator, opening, test, score, subject, number, _, grade, closing = cells[:9]

            # Ignore empty rows and table headers.
            if tr.find("th"):
                continue

            # Skip blank requirement rows.
            if not any((test, score, subject, number, grade)):
                continue

            # Resolve the canonical subject to its short course code.
            subject_code = lexicon_resolver.resolve_course_code(subject) or subject

            requirement = f"{subject_code}{number}" if number else subject_code

            details = []
            if grade:
                details.append(f"minimum grade: {grade}")
            if test:
                details.append(f"test: {test}")
            if score:
                details.append(f"score: {score}")

            if details:
                requirement += f" ({', '.join(details)})"

            if operator:
                lines.append("    " * depth + operator.upper())

            # Preserve grouping from the LORIS parentheses columns.
            if opening:
                lines.append("    " * depth + opening)
                depth += opening.count("(")

            lines.append("    " * depth + requirement)

            if closing:
                depth = max(0, depth - closing.count(")"))
                lines.append("    " * depth + closing)

    return "\n".join(lines) or None

def build_course_payload(section: dict[str, Any], term_code: str, canonical_subject: str) -> CourseCreate:
    subject_code = clean_text_value(section.get("subject")) or ""
    course_number = clean_text_value(section.get("courseNumber")) or ""
    campus = clean_text_value(section.get("campusDescription")) or "Waterloo"
    governing_year = term_code_to_academic_year(term_code)

    # Minimal course definition for insert
    # All relevant info in the course term
    return CourseCreate(
        academic_year=governing_year,
        institution=parse_institution(campus),
        campus=campus,
        calendar_url=None,
        subject_code=subject_code,
        course_number=course_number,
        title=clean_text_value(section.get("courseTitle")),
        description=None,
        needs_embedding=False,
        subject=canonical_subject,
        prereq=None,
        coreq=None,
        notes=None,
        exclusions=None,
        metadata_json={}
    )

def parse_faculty(raw: dict[str, Any]) -> CourseFaculty:
    """One LORIS faculty entry -> CourseFaculty."""
    banner_id = raw.get("bannerId")
    return CourseFaculty(
        bannerId=str(banner_id) if banner_id is not None else None,
        displayName=clean_text_value(raw.get("displayName")),
        emailAddress=clean_text_value(raw.get("emailAddress")),
        primaryIndicator=raw.get("primaryIndicator"),
    )


def _faculty_identity(faculty: CourseFaculty) -> str | None:
    """Who this person is, for de-duplication: Banner id, else email, else name.
    None means there is nothing to identify (or show), so the entry is dropped."""
    if faculty.bannerId:
        return f"id:{faculty.bannerId}"
    if faculty.emailAddress:
        return f"email:{faculty.emailAddress.casefold()}"
    if faculty.displayName:
        return f"name:{faculty.displayName.casefold()}"
    return None


def _merge_primary(first: bool | None, second: bool | None) -> bool | None:
    """True if either copy says primary; otherwise the known value; None only if neither says.
    (Never turns "not stated" into "not primary".)"""
    if first or second:
        return True
    return first if first is not None else second


def merge_faculty(*lists: list[CourseFaculty]) -> list[CourseFaculty]:
    """Merge instructor lists into one, listing each person once.

    LORIS has two lists per section: section["faculty"] (everyone teaching the section, filled by the
    class search) and meetingsFaculty[].faculty (who teaches each meeting, empty in class-search
    results but filled by Banner's per-section meeting endpoint). Pass the section list first: it is
    the base, and later lists only add people or missing details.

      - Same person (see _faculty_identity) appears once; empty fields are filled from later copies.
      - Primary if ANY copy marks them primary.
      - Primary instructors first, otherwise first-seen order.
    """
    merged: dict[str, CourseFaculty] = {}

    for faculty_list in lists:
        for faculty in faculty_list:
            identity = _faculty_identity(faculty)
            if identity is None:
                continue

            existing = merged.get(identity)
            if existing is None:
                merged[identity] = faculty
                continue

            # Same person again: keep known values, fill gaps, and keep "primary" if either says so.
            merged[identity] = existing.model_copy(update={
                "bannerId": existing.bannerId or faculty.bannerId,
                "displayName": existing.displayName or faculty.displayName,
                "emailAddress": existing.emailAddress or faculty.emailAddress,
                "primaryIndicator": _merge_primary(existing.primaryIndicator, faculty.primaryIndicator),
            })

    # sorted() is stable: within primary / non-primary, first-seen order is kept.
    return sorted(merged.values(), key=lambda faculty: not faculty.primaryIndicator)


def has_meeting_faculty(section: dict[str, Any]) -> bool:
    """Whether LORIS filled any per-meeting instructor list (empty in class-search results)."""
    return any(item.get("faculty") for item in section.get("meetingsFaculty") or [])


def build_course_term_payload(
        section: dict[str, Any],
        course_id: int,
        term_code: str,
        restrictions_text: str | None,
        description: RegistrationDescription,
        canonical_subject: str,
) -> CourseTermCreate:
    meetings_faculty = section.get("meetingsFaculty") or []
    meetings = []
    meeting_faculty_lists: list[list[CourseFaculty]] = []

    for item in meetings_faculty:
        meeting_times = item.get("meetingTime") or {}
        # Who teaches this meeting. Empty in class-search results; see merge_faculty().
        meeting_faculty = merge_faculty([parse_faculty(raw) for raw in item.get("faculty") or []])
        meeting_faculty_lists.append(meeting_faculty)

        meetings.append(
            CourseMeetingTime(
                beginTime=clean_text_value(meeting_times.get("beginTime")),
                endTime=clean_text_value(meeting_times.get("endTime")),
                building=clean_text_value(meeting_times.get("building")),
                room=clean_text_value(meeting_times.get("room")),
                **{day.value: meeting_times.get(day.value) for day in Weekday},
                startDate=clean_text_value(meeting_times.get("startDate")),
                endDate=clean_text_value(meeting_times.get("endDate")),
                category=clean_text_value(meeting_times.get("category")),
                scheduleType=clean_text_value(meeting_times.get("scheduleType")),
            )
        )

    # Section instructors: the section-level list is the base (built once, outside the meeting loop,
    # so a lecture + lab section never lists the same professor twice), plus anyone found only on a meeting.
    faculties = merge_faculty(
        [parse_faculty(raw) for raw in section.get("faculty") or []],
        *meeting_faculty_lists,
    )

    return CourseTermCreate(
        course_id=course_id,
        term_code=clean_text_value(term_code) or term_code,
        term_name=clean_text_value(section.get("termDesc")),
        crn=clean_text_value(section.get("courseReferenceNumber")) or "",

        subject_code=clean_text_value(section.get("subject")) or "",
        course_number=clean_text_value(section.get("courseNumber")) or "",
        title=clean_text_value(section.get("courseTitle")),
        subject=canonical_subject,

        section_code=clean_text_value(section.get("sequenceNumber")),
        part_of_term=clean_text_value(section.get("partOfTerm")),
        schedule_type=clean_text_value(section.get("scheduleTypeDescription")),
        open_section=section.get("openSection"),
        instructional_method=clean_text_value(section.get("instructionalMethodDescription")),
        description=description.description,
        prereq=description.prereq,
        coreq=description.coreq,
        exclusions=description.exclusions,
        notes=description.notes,
        restrictions=restrictions_text,
        maximum_enrollment=section.get("maximumEnrollment"),
        enrollment=section.get("enrollment"),
        seats_available=section.get("seatsAvailable"),
        wait_capacity=section.get("waitCapacity"),
        wait_count=section.get("waitCount"),
        wait_available=section.get("waitAvailable"),
        meetings=meetings,
        faculty=faculties,
        credit_hours=section.get("creditHours"),
        credit_hour_low=section.get("creditHourLow"),
        credit_hour_high=section.get("creditHourHigh"),
        metadata_json=CourseTermMetadata(
            campusDescription=clean_text_value(section.get("campusDescription")),
            instructionalMethod=clean_text_value(section.get("instructionalMethod")),
        ),
    )

