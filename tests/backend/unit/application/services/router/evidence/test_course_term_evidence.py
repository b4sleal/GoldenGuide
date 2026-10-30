from backend.application.services.router.evidence.course_term_evidence import (
    course_term_evidence,
    meeting_days,
    meeting_time,
)
from backend.domain.entities.wlu.loris_registration import (
    CourseMeetingTime,
    CourseTermRead,
)
from tests.backend.unit.application.services.router.factories import INSTITUTION

REGISTRATION_URL = str(INSTITUTION.registration_url)


def section(id_, section_code, **fields):
    return CourseTermRead(
        id=id_, course_id=1, term_code="202609", term_name="Fall 2026", crn=str(1000 + id_),
        subject="Computer Science", subject_code="CP", course_number="220", section_code=section_code, **fields,
    )


def test_sources_link_to_loris_registration():
    [evidence] = course_term_evidence([section(7, "A")], primary=True, registration_url=REGISTRATION_URL)
    assert evidence.url == REGISTRATION_URL
    assert evidence.source_id == "course_term:7"


def test_meeting_cells():
    meeting = CourseMeetingTime(monday=True, wednesday=True, friday=True, beginTime="1000", endTime="1120")
    assert meeting_days(meeting) == "Mon/Wed/Fri"
    assert meeting_time(meeting) == "10:00–11:20"
    assert meeting_days(CourseMeetingTime()) == "—"


def test_text_shared_by_every_section_is_printed_once():
    sections = [section(1, "A", description="Data structures."), section(2, "B", description="Data structures.")]
    first, second = course_term_evidence(sections, primary=True, registration_url=REGISTRATION_URL)

    assert "Description (shared across retrieved sections of this course/term): Data structures." in first.content
    assert "Description" not in second.content
    assert first.table_row.group == second.table_row.group == "CP220 sections — Fall 2026"


def test_table_content_is_one_line_per_section_with_shared_text_once():
    meeting = CourseMeetingTime(monday=True, wednesday=True, beginTime="1000", endTime="1120")
    sections = [
        section(1, "A", description="Data structures.", schedule_type="Lecture", meetings=[meeting],
                open_section=True, seats_available=12, restrictions="BSc students only"),
        section(2, "B", description="Data structures.", open_section=False),
    ]
    first, second = course_term_evidence(sections, primary=True, registration_url=REGISTRATION_URL)

    assert first.table_content.splitlines() == [
        (
            "Course: CP220 | Term: Fall 2026 | Section: A (Lecture) | Mon/Wed 10:00–11:20 | Unknown | "
            "Instructor: TBA (not yet assigned) | Open, seats: 12"
        ),
        "Restrictions: BSc students only",
        "Description (shared across retrieved sections of this course/term): Data structures.",
    ]
    assert second.table_content == (
        "Course: CP220 | Term: Fall 2026 | Section: B (Unknown) | No scheduled meetings | Unknown | "
        "Instructor: TBA (not yet assigned) | Closed, seats: Unknown"
    )


def test_empty_section_fields_are_named_once():
    [evidence] = course_term_evidence(
        [section(1, "A", title="Digital Electronics", prereq="CP164")], primary=True, registration_url=REGISTRATION_URL,
    )
    assert "Prerequisites: CP164" in evidence.content
    assert evidence.content.splitlines()[-1] == (
        "Not listed in the LORIS section record: restrictions, description, corequisites, exclusions"
    )
    assert "Not specified" not in evidence.content


def test_shared_fields_are_not_reported_missing_on_later_sections():
    sections = [section(1, "A", description="Data structures."), section(2, "B", description="Data structures.")]
    _, second = course_term_evidence(sections, primary=True, registration_url=REGISTRATION_URL)
    assert "description" not in second.content.splitlines()[-1]


def test_unassigned_instructor_reads_tba():
    [evidence] = course_term_evidence([section(1, "A")], primary=False, registration_url=REGISTRATION_URL)
    assert "Instructor: TBA (not yet assigned)" in evidence.content
    assert evidence.table_row.cells["Instructor"] == "TBA"
    assert evidence.primary is False
