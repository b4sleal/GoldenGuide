from backend.application.services.router.evidence.course_evidence import course_evidence
from backend.domain.entities.wlu.course import CourseMetadata, CourseRead


def course(**overrides):
    fields = {
        "id": 1, "academic_year": "2026/2027", "subject": "Computer Science", "subject_code": "CP",
        "course_number": "104", "institution": "WLU", "campus": "Waterloo", "title": "Introduction to Programming",
        "credit_min": 0.5, "credit_max": 0.5, "credit_unit": "credits", "metadata_json": CourseMetadata(),
    }
    return CourseRead(**{**fields, **overrides})


def test_courses_of_one_subject_and_year_share_a_table():
    first = course_evidence(course(), primary=True)
    second = course_evidence(course(id=2, course_number="213"), primary=True)

    assert first.table_row.group == second.table_row.group == "Computer Science courses — 2026/2027"
    assert first.table_row.cells == {"Course": "CP104", "Title": "Introduction to Programming", "Credits": "0.5"}


def test_empty_fields_are_named_once_instead_of_listed_as_not_specified():
    evidence = course_evidence(course(description="Intro to Python.", prereq="CP102"), primary=True)

    lines = evidence.content.splitlines()
    assert "Prerequisites: CP102" in lines and "Description: Intro to Python." in lines
    assert lines[-1] == "Not listed in the Academic Calendar record: corequisites, exclusions, notes"
    assert "Not specified" not in evidence.content
    assert evidence.compact_content.splitlines()[-1] == "Not listed in the Academic Calendar record: corequisites, exclusions"


def test_a_complete_record_has_no_not_listed_line():
    evidence = course_evidence(
        course(description="D", prereq="P", coreq="C", exclusions="E", notes="N"), primary=True,
    )
    assert "Not listed" not in evidence.content


def test_missing_values_render_as_dashes():
    evidence = course_evidence(course(subject="", title=None, credit_min=None, credit_max=None, credit_unit=None), primary=True)

    assert evidence.table_row.group == "CP courses — 2026/2027"
    assert evidence.table_row.cells == {"Course": "CP104", "Title": "—", "Credits": "—"}
