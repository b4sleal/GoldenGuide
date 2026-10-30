"""Keep URLs out of the model's context and put them back in the streamed answer.

Course codes get links to their Academic Calendar page; @@n@@ placeholders become the URLs
registered for this request. Text that may be an unfinished link or code is held until the next chunk.
"""
import re
from collections.abc import Iterable
from urllib.parse import urlparse


class ChatbotLinkResolver:
    COURSE_LINK = re.compile(
        r"\[([A-Z]{2}\d{3}[A-Z]?)\]\((https?://[^)\s]+)\)",
        re.IGNORECASE,
    )
    SOURCE_COURSE = re.compile(
        r"^([A-Z]{2}\d{3}[A-Z]?)\b",
        re.IGNORECASE,
    )

    # Match complete Markdown links before matching individual course codes.
    OUTPUT_TOKEN = re.compile(
        r"(?P<link>\[[^\]\n]*\]\s*\\?\([^)\n]*\))"
        r"|(?P<bracket>\[(?P<bracket_code>[A-Z]{2}\d{3}[A-Z]?)\])"
        r"|(?P<inline>`(?P<inline_code>[A-Z]{2}\d{3}[A-Z]?)`)"
        r"|(?P<code>(?<![A-Z0-9])[A-Z]{2}\d{3}[A-Z]?(?![A-Z0-9]))",
        re.IGNORECASE,
    )
    PLACEHOLDER_LINK = re.compile(
        r"\]\s*\\?\(\s*@@(\d+)@@\s*\\?\)"
    )

    # Retain incomplete Markdown links and course codes between chunks.
    PARTIAL = re.compile(
        r"\[[^\]\n]*(?:\](?:\\?\([^)\n]*)?)?$"
        r"|(?<![A-Z0-9])[A-Z]{1,2}\d{0,3}[A-Z]?$",
        re.IGNORECASE,
    )

    def __init__(self):
        self.course_links: dict[str, str] = {}
        self.placeholder_links: dict[str, str] = {}
        self.ambiguous: set[str] = set()
        self.buffer = ""

    @staticmethod
    def _is_course_url(url: str) -> bool:
        parsed = urlparse(url)
        return (
                parsed.scheme == "https"
                and parsed.hostname == "academic-calendar.wlu.ca"
                and parsed.path == "/course.php"
        )

    def _register_course(self, code: str, url: str) -> None:
        code = code.upper()
        url = url.replace(r"\&", "&")

        if not self._is_course_url(url) or code in self.ambiguous:
            return

        existing = self.course_links.get(code)

        if existing is not None and existing != url:
            self.ambiguous.add(code)
            self.course_links.pop(code, None)
            return

        self.course_links[code] = url

    def register_sources(self, sources: Iterable) -> None:
        for source in sources:
            url = source.url
            title = source.title or ""

            if not url or not self._is_course_url(url):
                continue

            match = self.SOURCE_COURSE.match(title.strip())
            if match:
                self._register_course(match.group(1), url)

    def register_links(self, links: dict[str, str]) -> None:
        self.placeholder_links.update(links)

    def prepare_context(self, context: str, sources=()) -> str:
        """Register course URLs while keeping the model's context URL-free."""
        self.register_sources(sources)

        def replace(match: re.Match) -> str:
            code, url = match.group(1), match.group(2)

            if not self._is_course_url(url):
                return match.group(0)

            self._register_course(code, url)
            return code

        return self.COURSE_LINK.sub(replace, context)

    def _resolve_text(self, text: str) -> str:
        def replace(match: re.Match) -> str:
            if match.group("link") is not None:
                original = match.group("link")

                def resolve_placeholder(link_match: re.Match) -> str:
                    url = self.placeholder_links.get(link_match.group(1))

                    if not url:
                        return "]"

                    return f"]({url})"

                return self.PLACEHOLDER_LINK.sub(
                    resolve_placeholder,
                    original,
                )

            code = (
                    match.group("bracket_code")
                    or match.group("inline_code")
                    or match.group("code")
            )
            url = self.course_links.get(code.upper())

            if not url:
                return match.group(0)

            return f"[{code}]({url})"

        return self.OUTPUT_TOKEN.sub(replace, text)

    def _text_event(self, text: str) -> dict:
        return {
            "type": "text",
            "text": self._resolve_text(text),
        }

    def feed(self, chunk: str) -> list[dict]:
        self.buffer += chunk

        if not self.buffer:
            return []

        match = self.PARTIAL.search(self.buffer)
        split_at = match.start() if match else len(self.buffer)

        ready = self.buffer[:split_at]
        self.buffer = self.buffer[split_at:]

        return [self._text_event(ready)] if ready else []

    def flush(self) -> list[dict]:
        if not self.buffer:
            return []

        text = self.buffer
        self.buffer = ""

        return [self._text_event(text)]