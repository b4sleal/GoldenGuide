"""Academic Calendar HTML -> record type, page text, course header/details, breadcrumbs. Pure functions.

Links in extracted text become one-based @@n@@ placeholders pointing into the page's external_links,
resolved later when the text is shown (AcademicLinkResolver / the chat link resolver).
"""
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag

from backend.domain.settings.profiles import WluLexicon
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.application.use_cases.scraping.common_parsing import (
    clean_html_to_markdown, extract_page_links, normalize_text
)


# -------------------------
# URL CLASSIFICATION
# -------------------------

def classify_calendar_url(
        url: str, faculty: str | None, departments: list[str], is_faculty_crumb: bool, lexicon_profile: WluLexicon,
) -> AcademicCalendarType:
    """Record type from the URL path; only the remaining (section) pages are checked against the lexicon.

    Typed URLs come first, so neither a lexicon entry nor a department named like its faculty (Martin
    Luther University College) can turn a course, program or department into a faculty.
    `is_faculty_crumb`: the page's own breadcrumb entry is its faculty (the trail is only the faculty).
    Faculty sub-pages also have no crumbs between the faculty and themselves, so "no departments"
    alone does not make a faculty page.
    """
    path = urlparse(url).path.lower()
    if path.endswith("/department.php"):
        return AcademicCalendarType.DEPARTMENT
    if path.endswith("/program.php"):
        return AcademicCalendarType.PROGRAM
    if path.endswith("/course.php"):
        return AcademicCalendarType.COURSE
    if path.endswith("/glossary.php"):
        return AcademicCalendarType.GLOSSARY

    faculty_names = { e.canonical.lower() for e in lexicon_profile.faculties.values() }
    if is_faculty_crumb and faculty and faculty.strip().lower() in faculty_names:
        return AcademicCalendarType.FACULTY

    if departments and departments[-1].strip().lower() in faculty_names:
        return AcademicCalendarType.FACULTY

    return AcademicCalendarType.PAGE


# -------------------------
# PAGE CONTENT EXTRACTORS
# -------------------------

def parse_page_content(html_content: str, url: str) -> tuple[str, str, list[str]]:
    """Returns the main body text, primary title, and external links."""
    soup = BeautifulSoup(html_content, "html.parser")
    root = soup.select_one("div.content") or soup.body or soup

    for el in root.select(".returntotop"):
        el.decompose()

    h1 = root.find("h1")
    if h1:
        title = normalize_text(h1.get_text(" ", strip=True))
    else:
        title = normalize_text(soup.title.get_text(" ", strip=True) if soup.title else "")

    external_links = extract_page_links(root, url)

    # Pass the raw HTML block string to the shared parser
    text = clean_html_to_markdown(str(root), url, external_links) or ""

    return text, title, external_links


def parse_department_contact(html_content: str, url: str, page_links: list[str]) -> str | None:
    """The department contact box as Markdown; its links are appended to `page_links`."""
    soup = BeautifulSoup(html_content, "html.parser")
    dept = soup.select_one("#deptcontact")

    if not dept:
        return None

    for el in dept.select(".returntotop"):
        el.decompose()

    extract_page_links(dept, url, existing_links=page_links)

    # Pass the raw HTML block string to the shared parser
    return clean_html_to_markdown(str(dept), url, page_links)


# -------------------------
# COURSE EXTRACTORS
# -------------------------

def parse_course(html_content: str, url: str, external_links: list[str]) -> str | None:
    """The course description as Markdown, without the heading and the additional-information list."""
    soup = BeautifulSoup(html_content, "html.parser")
    root = soup.select_one("div.content") or soup.body

    if not root:
        return None

    # Remove return-to-top elements
    for el in root.select(".returntotop"):
        el.decompose()

    # Remove the course heading (code, title, credits)
    h1 = root.find("h1")
    if h1:
        h1.decompose()

    # Remove the Additional Course Information section
    heading = root.find(
        lambda tag: (
                tag.name == "div"
                and tag.get_text(" ", strip=True).casefold().rstrip(":")
                == "additional course information"
        )
    )

    if heading:
        # Remove heading and its associated details
        details = heading.find_next_sibling("dl")
        if details:
            details.decompose()

        heading.decompose()

    # Extract links from the remaining description
    text = clean_html_to_markdown(str(root), url, external_links) or ""

    return text

def parse_course_header(html_content: str) -> tuple[str, str, str, dict] | None:
    """
    Extracts Subject, Number, Title, and Credit JSON directly from the Course Page H1.
    Expects HTML structure: <h1>CP120<br>Intro to computer stuff<br>0.5 credit</h1>
    """
    soup = BeautifulSoup(html_content, "html.parser")
    root = soup.select_one("div.content, #content") or soup.body
    h1 = root.find("h1") if root else None
    if h1 is None:
        return None  # Not a course page layout: the caller skips it.

    # .stripped_strings natively splits text wherever a <br> tag appears
    parts = list(h1.stripped_strings)

    # Part 1: Subject and Code (e.g., "CP120" or "CP 120")
    match = re.search(r"([A-Za-z]{2,5})\s*(\d{3,5}[A-Za-z]?)", parts[0]) if parts else None
    if match is None:
        return None

    subject = match.group(1).upper()
    course_number = match.group(2).upper()

    # Part 2: Title
    title = parts[1] if len(parts) > 1 else ""
    credit_json = {}

    # Part 3: Credit JSON
    if len(parts) > 2:
        cred_match = re.search(r"(\d\.\d+)", parts[2])
        if cred_match:
            val = float(cred_match.group(1))
            credit_json = {"min": val, "max": val, "unit": "credits"}

    return subject, course_number, title, credit_json


def parse_breadcrumbs(html_content: str) -> tuple[str | None, list[str], str | None]:
    """Extracts faculty and departments from the breadcrumb trail."""
    soup = BeautifulSoup(html_content, "html.parser")
    breadcrumb = soup.select_one(".breadcrumb")

    if not breadcrumb:
        return None, [], None

    links = [a.get_text(strip=True) for a in breadcrumb.find_all("a") if a.get_text(strip=True)]
    return (links[0], links[1:-1], links[-1]) if links else (None, [], None)


def parse_additional_course_information(
        html_content: str,
        url: str,
        external_links: list[str] | None = None
) -> dict[str, str | None]:
    """Prerequisites, corequisites, exclusions and notes from the course page's
    "Additional Course Information" list; a field the page does not have stays None."""
    soup = BeautifulSoup(html_content, "html.parser")
    result: dict[str, str | None] = {
        "prereq": None,
        "coreq": None,
        "exclusions": None,
        "notes": None,
    }

    heading = soup.find(
        lambda tag: (
                tag.name == "div"
                and tag.get_text(" ", strip=True).casefold().rstrip(":")
                == "additional course information"
        )
    )
    if heading is None:
        return result

    details = heading.find_next_sibling()
    if details is None or details.name != "dl":
        return result

    def append(field: str, value: str) -> None:
        existing = result[field]
        result[field] = f"{existing}\n\n{value}" if existing else value

    for term in details.find_all("dt", recursive=False):
        label = term.get_text(" ", strip=True).casefold()
        # Normalize hyphens and spacing, including "pre-requisites".
        label = re.sub(r"[\s‐‑–—-]+", "", label)

        descriptions = []
        for sibling in term.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            if sibling.name == "dt":
                break
            if sibling.name == "dd":
                text = clean_html_to_markdown(str(sibling), url, external_links)
                if text:
                    descriptions.append(text)

        value = "\n\n".join(descriptions)
        if not value:
            continue

        # Independent checks: combined labels populate both fields.
        if "prerequisite" in label:
            append("prereq", value)
        if "corequisite" in label:
            append("coreq", value)
        if "exclusion" in label:
            append("exclusions", value)
        if "notes" in label:
            append("notes", value)

    return result