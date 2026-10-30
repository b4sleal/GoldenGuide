"""A website page -> title, body text and links. No structured extraction (unlike the calendar)."""
from dataclasses import dataclass

from bs4 import BeautifulSoup

from backend.application.use_cases.scraping.common_parsing import (
    clean_html_to_markdown,
    extract_page_links,
    normalize_text,
)
from backend.domain.settings.scraping import WebsiteScrapeSettings


@dataclass(frozen=True)
class WebsitePage:
    title: str
    content: str
    links: list[str]


def page_title(soup: BeautifulSoup, root, suffix: str | None) -> str:
    """The content's first h1, else <title> without the site suffix."""
    heading = root.find("h1")
    if heading:
        return normalize_text(heading.get_text(" ", strip=True))

    title = normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else ""
    if suffix and title.endswith(suffix.strip()):
        title = title[: -len(suffix.strip())].rstrip(" |")
    return title


def parse_website_page(html: str, url: str, settings: WebsiteScrapeSettings) -> WebsitePage | None:
    """None when the page has no content root (e.g. an error or landing template)."""
    soup = BeautifulSoup(html, "html.parser")
    root = soup.select_one(settings.content_selector)
    if root is None:
        return None

    for selector in settings.remove_selectors:
        for element in root.select(selector):
            element.decompose()

    links = extract_page_links(root, url)
    return WebsitePage(
        title=page_title(soup, root, settings.title_suffix),
        content=clean_html_to_markdown(str(root), url, links) or "",
        links=links,
    )
