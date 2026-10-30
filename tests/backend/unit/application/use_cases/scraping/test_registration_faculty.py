"""Instructors come from LORIS's section-level list, merged with any per-meeting lists, each person once."""
from backend.application.use_cases.scraping.wlu_registration.parse import (
    build_course_term_payload,
    has_meeting_faculty,
    merge_faculty,
    parse_faculty,
)
from backend.domain.entities.wlu.loris_registration import (
    CourseFaculty,
    RegistrationDescription,
)

MERGLER = {"bannerId": "38321", "displayName": "Iga Mergler", "emailAddress": "imergler@wlu.ca", "primaryIndicator": True}


def meeting(days: dict, faculty: list) -> dict:
    return {"faculty": faculty, "meetingTime": {"beginTime": "1000", "endTime": "1120", **days}}


def section(faculty: list, meetings: list) -> dict:
    """Shaped like a real entry from loris/terms/202701.json (class-search results)."""
    return {
        "term": "202701", "termDesc": "Winter 2027", "courseReferenceNumber": "1078",
        "subject": "CP", "courseNumber": "220", "sequenceNumber": "A",
        "faculty": faculty, "meetingsFaculty": meetings,
    }


def payload(raw_section: dict):
    return build_course_term_payload(
        section=raw_section, course_id=1, term_code="202701", restrictions_text=None,
        description=RegistrationDescription(), canonical_subject="Computer Science",
    )


def test_section_level_faculty_is_used_when_meeting_lists_are_empty():
    # Regression: instructors were read only from meetingsFaculty[].faculty, which class search
    # leaves empty, so every section was stored with no instructor.
    result = payload(section([MERGLER], [meeting({"monday": True}, []), meeting({"thursday": True}, [])]))
    assert [f.displayName for f in result.faculty] == ["Iga Mergler"]


def test_same_professor_on_section_and_every_meeting_is_listed_once():
    result = payload(section([MERGLER], [meeting({"monday": True}, [MERGLER]), meeting({"thursday": True}, [MERGLER])]))
    assert [f.bannerId for f in result.faculty] == ["38321"]


def test_meeting_level_faculty_is_detected_on_the_raw_section():
    # Meetings no longer carry instructors (the section list merges them), so the LORIS
    # shape check reads the raw section instead.
    assert has_meeting_faculty(section([], [meeting({"monday": True}, [MERGLER])]))
    assert not has_meeting_faculty(section([MERGLER], [meeting({"monday": True}, [])]))
    assert not has_meeting_faculty(section([MERGLER], []))


def test_lab_instructor_only_on_a_meeting_is_added():
    ta = {"bannerId": "99", "displayName": "Lab TA", "primaryIndicator": False}
    result = payload(section([MERGLER], [meeting({"monday": True}, []), meeting({"thursday": True}, [ta])]))
    assert [f.displayName for f in result.faculty] == ["Iga Mergler", "Lab TA"]


def test_no_faculty_anywhere_is_tba_not_an_error():
    assert payload(section([], [meeting({"monday": True}, [])])).faculty == []


def test_merge_identity_falls_back_to_email_then_name_and_keeps_primary():
    merged = merge_faculty(
        [CourseFaculty(displayName="A. Smith", emailAddress="ASmith@wlu.ca", primaryIndicator=False),
         CourseFaculty(displayName="Kim Lee")],
        [CourseFaculty(emailAddress="asmith@wlu.ca", primaryIndicator=True),   # same as A. Smith (email, any case)
         CourseFaculty(displayName="kim lee"),                                 # same as Kim Lee (name)
         CourseFaculty()],                                                     # nothing to identify: dropped
    )
    assert [(f.displayName, f.primaryIndicator) for f in merged] == [("A. Smith", True), ("Kim Lee", None)]


def test_primary_instructor_is_listed_first():
    merged = merge_faculty([
        parse_faculty({"bannerId": "1", "displayName": "Co-instructor", "primaryIndicator": False}),
        parse_faculty(MERGLER),
    ])
    assert [f.displayName for f in merged] == ["Iga Mergler", "Co-instructor"]
