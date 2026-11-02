"""Academic Calendar record types: breadcrumbs shaped like the live calendar's (the last crumb is the page)."""
import pytest

from backend.application.use_cases.scraping.academic_calendar.scrape.parse import (
    classify_calendar_url,
    parse_breadcrumbs,
)
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.settings.profiles import LexiconEntry, WluLexicon

FACULTY = "Lazaridis School of Business and Economics"
LEXICON = WluLexicon(
    faculties={"lazaridis": LexiconEntry(canonical=FACULTY, aliases=[])},
    departments={},
    registration_notes={},
)
BASE = "https://academic-calendar.wlu.ca"


def breadcrumb_html(*crumbs: str) -> str:
    links = "".join(f'<a href="#">{crumb}</a>' for crumb in crumbs)
    return f'<html><body><div class="breadcrumb">{links}</div></body></html>'


def classify(url: str, *crumbs: str) -> AcademicCalendarType:
    # Mirrors persistence.py: the faculty resolves through the lexicon (here it already is canonical).
    faculty, departments, current = parse_breadcrumbs(breadcrumb_html(*crumbs))
    is_faculty_crumb = not departments and current == faculty
    return classify_calendar_url(url, faculty, departments, is_faculty_crumb, LEXICON)


@pytest.mark.parametrize(
    ("url", "crumbs", "expected"),
    [
        ("/section.php?cal=1&s=934&y=79", [FACULTY], AcademicCalendarType.FACULTY),
        # Directly under the faculty, like a faculty page, but the page is not the faculty itself.
        ("/department.php?cal=1&d=2110&s=934&y=79", [FACULTY, "Business and Economics"], AcademicCalendarType.DEPARTMENT),
        ("/section.php?cal=1&s=934&ss=3873&y=79", [FACULTY, "Academic Advising"], AcademicCalendarType.PAGE),
        (
            "/program.php?cal=1&d=2110&p=4587&s=934&y=79",
            [FACULTY, "Business and Economics", "Business (Brantford Campus)", "Honours Bachelor of Business Technology Management (Brantford)"],
            AcademicCalendarType.PROGRAM,
        ),
    ],
    ids=["faculty", "department", "faculty-sub-page", "program"],
)
def test_record_type_follows_the_pages_own_crumb(url, crumbs, expected):
    assert classify(BASE + url, *crumbs) == expected


def test_a_department_named_like_its_faculty_is_still_a_department():
    # Martin Luther University College's department has the faculty's name: [MLUC, MLUC].
    url = f"{BASE}/department.php?cal=3&d=3345&s=1194&y=94"
    assert classify(url, FACULTY, FACULTY) == AcademicCalendarType.DEPARTMENT


def test_a_department_listed_as_a_faculty_in_the_lexicon_does_not_change_typed_pages():
    # Public Safety was once listed under faculties; its courses must still be stored as courses.
    lexicon = LEXICON.model_copy(update={
        "faculties": {**LEXICON.faculties, "public_safety": LexiconEntry(canonical="Public Safety", aliases=[])},
    })
    faculty, departments, _ = parse_breadcrumbs(breadcrumb_html(FACULTY, "Public Safety", "SAFE602"))
    url = f"{BASE}/course.php?c=81939&cal=3&d=3352&s=1201&y=94"

    assert classify_calendar_url(url, faculty, departments, False, lexicon) == AcademicCalendarType.COURSE


def test_breadcrumb_splits_faculty_parents_and_the_page_itself():
    html = breadcrumb_html(FACULTY, "Business & Economics", "Business (Waterloo Campus)", "BU111")
    assert parse_breadcrumbs(html) == (FACULTY, ["Business & Economics", "Business (Waterloo Campus)"], "BU111")
