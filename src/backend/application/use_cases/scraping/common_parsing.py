"""HTML -> clean Markdown helpers shared by every scraper (calendar, websites, LORIS)."""
import html
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup, NavigableString, Tag, Comment

BLOCK_TAGS = {
    "p", "div", "section", "article", "header", "footer",
    "main", "aside", "nav", "address", "blockquote",
    "figure", "figcaption",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "dl", "dt", "dd",
}

def clean_text_value(value: object) -> str | None:
    """Cleans basic string values (removes NBSP, trims whitespace, unescapes)."""
    if value is None:
        return None
    text = str(value).strip().replace('\xa0', ' ').replace('\u200b', '')
    if not text:
        return None
    return html.unescape(" ".join(text.split())) or None

def normalize_text(text: str) -> str:
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()

def normalize_block_text(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    lines = text.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
        elif stripped.startswith("• "):
            cleaned_lines.append("  " + stripped)
        else:
            cleaned_lines.append(stripped)

    text = "\n".join(cleaned_lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def extract_page_links(soup_node, base_url: str, existing_links: list[str] | None = None) -> list[str]:
    links = existing_links if existing_links is not None else []
    if not soup_node:
        return links
    for a_tag in soup_node.find_all("a", href=True):
        href = a_tag["href"].strip()
        link_text = a_tag.get_text(" ", strip=True)
        if href.startswith(("#", "javascript:")) or not link_text:
            continue
        absolute_url = urljoin(base_url, href)
        if absolute_url not in links:
            links.append(absolute_url)
    return links

def _render_node(node) -> str:
    if isinstance(node, Comment):
        return ""

    if isinstance(node, NavigableString):
        # Source formatting is whitespace; <br> supplies actual line breaks.
        return str(node).replace("\r", " ").replace("\n", " ")

    if not isinstance(node, Tag):
        return ""

    if node.name in {"script", "style", "template"}:
        return ""

    if node.name in {"br", "hr"}:
        return "\n"

    content = "".join(_render_node(child) for child in node.children)

    if node.name in {"td", "th"}:
        cell = content.strip().replace("\n", " ")
        return f" {cell} |"

    if node.name == "tr":
        return f"\n|{content}\n"

    if node.name == "table":
        return f"\n\n{content.strip()}\n\n"

    if node.name == "li":
        return f"• {content.strip()}\n" if content.strip() else ""

    if node.name in {"dt", "dd"}:
        return f"{content.strip()}\n" if content.strip() else ""

    if node.name in BLOCK_TAGS:
        return f"\n{content.strip()}\n" if content.strip() else ""

    # Inline elements retain their surrounding whitespace.
    return content

def clean_html_to_markdown(raw_html: str | None, base_url: str | None = None, extracted_links: list[str] | None = None) -> str | None:
    """Fully unescapes and cleans HTML into Markdown, preserving links if provided."""
    if not raw_html:
        return None

    # 1. Unescape FIRST! This prevents double-escaped LORIS HTML from leaking tags
    unescaped_html = html.unescape(raw_html)
    soup = BeautifulSoup(unescaped_html, "html.parser")

    # 2. Inject RAG citation links if requested
    if base_url and extracted_links is not None:
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            link_text = a_tag.get_text(" ", strip=True)
            if href.startswith(("#", "javascript:")) or not link_text:
                continue
            absolute_url = urljoin(base_url, href)
            if absolute_url in extracted_links:
                link_id = extracted_links.index(absolute_url) + 1
                a_tag.replace_with(f"[{link_text}](@@{link_id}@@)")

    # 3. Render block layout and clean
    text = _render_node(soup)
    cleaned_text = normalize_block_text(text)

    return cleaned_text or None