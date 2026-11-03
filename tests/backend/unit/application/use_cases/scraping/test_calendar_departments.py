"""Calendar departments: names without the heading subtitle, canonical when the lexicon lists them."""
import pytest

from backend.application.use_cases.scraping.academic_calendar.profile import AcademicCalendarProfile
from backend.application.use_cases.scraping.academic_calendar.scrape.parse import parse_page_content
from backend.application.use_cases.scraping.academic_calendar.scrape.persistence import parse_calendar_batch
from backend.domain.entities.scraping import ScrapePageRead
from backend.domain.entities.wlu.academic_level import AcademicLevel
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.settings.profiles import LexiconEntry, WluLexicon

BASE = "https://academic-calendar.wlu.ca"
LEXICON = WluLexicon(
    faculties={"arts": LexiconEntry(canonical="Faculty of Arts", aliases=["arts"])},
    departments={"arabic": LexiconEntry(canonical="Arabic", course_code="AB", aliases=["arabic (lang/lit)"])},
    registration_notes={},
)
RESOLVER = WluLexiconResolver(LEXICON)

# Shaped like the live calendar (department.php?cal=1&d=3233&s=1169&y=93).
DEPARTMENT_HTML = """<html><body>
<div class="breadcrumb"><a href="section.php">Faculty of Arts</a><a href="department.php">Arabic (Lang/Lit)</a></div>
<div class="content">
<h1>Arabic (Lang/Lit)<br/><span class="subtitle">Department of Languages and Literatures</span></h1>
<p>Arabic language and literature courses.</p>
</div></body></html>"""


def course_html(*crumbs: str) -> str:
    links = "".join(f'<a href="#">{crumb}</a>' for crumb in crumbs)
    return f"""<html><body><div class="breadcrumb">{links}</div>
<div class="content"><h1>AB101<br/>Introductory Arabic<br/>0.5 Credit</h1><p>An introduction to Arabic.</p></div>
</body></html>"""


def parse(url: str, html: str):
    page = ScrapePageRead(id=1, url=url, site_name="academic_calendar_wlu", status="success", blob_key="key")
    return parse_calendar_batch([page], {"key": html.encode()}, "2026/2027", RESOLVER, LEXICON)


def test_heading_subtitle_is_left_out_of_the_title_but_kept_in_the_text():
    text, title, _ = parse_page_content(DEPARTMENT_HTML, f"{BASE}/department.php")
    assert title == "Arabic (Lang/Lit)"
    assert "Department of Languages and Literatures" in text


def test_department_page_is_saved_under_the_lexicons_canonical_name():
    batch = parse(f"{BASE}/department.php?cal=1&d=3233&s=1169&y=93", DEPARTMENT_HTML)

    (record,) = batch.academic_records
    assert record.record_type == AcademicCalendarType.DEPARTMENT
    assert record.title == "Arabic"


def test_department_missing_from_the_lexicon_keeps_its_calendar_name():
    html = DEPARTMENT_HTML.replace("Arabic (Lang/Lit)", "Business (Brantford Campus)")
    batch = parse(f"{BASE}/department.php?cal=1&d=1&s=1&y=93", html)

    assert batch.academic_records[0].title == "Business (Brantford Campus)"


@pytest.mark.parametrize(
    ("url", "level"),
    [
        (f"{BASE}/department.php?cal=1&d=3233&s=1169&y=93", AcademicLevel.UNDERGRADUATE),
        (f"{BASE}/course.php?c=81939&cal=3&d=3352&s=1201&y=94", AcademicLevel.GRADUATE),
        (f"{BASE}/department.php?cal=2&d=1&s=1&y=76", None),   # Unknown calendar.
        (f"{BASE}/department.php?xcal=1&d=1&s=1&y=93", None),  # No `cal` parameter.
    ],
    ids=["undergraduate", "graduate", "unknown-cal", "no-cal"],
)
def test_academic_level_comes_from_the_calendar_url(url, level):
    assert AcademicCalendarProfile.academic_level(url) == level


def test_parsed_records_carry_their_calendars_level():
    department = parse(f"{BASE}/department.php?cal=1&d=3233&s=1169&y=93", DEPARTMENT_HTML)
    course = parse(f"{BASE}/course.php?c=1&cal=3&d=3233&s=1169&y=94", course_html("Faculty of Arts", "Arabic (Lang/Lit)", "AB101"))

    assert department.academic_records[0].academic_level == AcademicLevel.UNDERGRADUATE
    assert course.course_payloads[0].academic_level == AcademicLevel.GRADUATE


def test_course_departments_are_canonical_or_their_calendar_names_never_empty():
    html = course_html("Faculty of Arts", "Arabic (Lang/Lit)", "Languages (Waterloo Campus)", "AB101")
    batch = parse(f"{BASE}/course.php?c=1&cal=1&d=3233&s=1169&y=93", html)

    (course,) = batch.course_payloads
    assert course.subject == "Arabic"
    assert course.metadata_json.departments == ["Arabic", "Languages (Waterloo Campus)"]
    assert course.metadata_json.faculty == "Faculty of Arts"
