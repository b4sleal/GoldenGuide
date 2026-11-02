"""Keep URLs out of the model's context and put them back in the streamed answer.

The context holds plain course codes, never Markdown links; each code with a known Academic Calendar
page becomes a link in the answer. Text that may be an unfinished link or code is held until the next
chunk.
"""
import re
from collections.abc import Iterable
from urllib.parse import urlparse

# A WLU course code: 2-4 subject letters, 3 digits, an optional suffix (CP164, GENG135, BU111A).
COURSE_CODE_PATTERN = r"[A-Z]{2,4}\d{3}[A-Z]?"


class ChatbotLinkResolver:
    COURSE_LINK = re.compile(
        rf"\[({COURSE_CODE_PATTERN})\]\((https?://[^)\s]+)\)",
        re.IGNORECASE,
    )
    SOURCE_COURSE = re.compile(
        rf"^({COURSE_CODE_PATTERN})\b",
        re.IGNORECASE,
    )

    # Match complete Markdown links before matching individual course codes.
    OUTPUT_TOKEN = re.compile(
        r"(?P<link>\[[^\]\n]*\]\s*\\?\([^)\n]*\))"
        rf"|(?P<bracket>\[(?P<bracket_code>{COURSE_CODE_PATTERN})\])"
        rf"|(?P<inline>`(?P<inline_code>{COURSE_CODE_PATTERN})`)"
        rf"|(?P<code>(?<![A-Z0-9]){COURSE_CODE_PATTERN}(?![A-Z0-9]))",
        re.IGNORECASE,
    )
    # A placeholder link the model should never see; if one still appears, only its label is shown.
    PLACEHOLDER_LINK = re.compile(
        r"\[([^\]\n]*)\]\s*\\?\(\s*@@\d+@@\s*\\?\)"
    )

    # Retain incomplete Markdown links and course codes between chunks.
    PARTIAL = re.compile(
        r"\[[^\]\n]*(?:\](?:\\?\([^)\n]*)?)?$"
        r"|(?<![A-Z0-9])[A-Z]{1,4}\d{0,3}[A-Z]?$",
        re.IGNORECASE,
    )

    def __init__(self):
        self.course_links: dict[str, str] = {}
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

    def register_course_links(self, links: dict[str, str]) -> None:
        """Course code -> calendar page links found in the evidence (e.g. prerequisites)."""
        for code, url in links.items():
            self._register_course(code, url)

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

                # A placeholder link: keep the label, linked if it is a known course code.
                placeholder = self.PLACEHOLDER_LINK.fullmatch(original)
                if placeholder is None:
                    return original
                label = placeholder.group(1)
                url = self.course_links.get(label.strip().upper())
                return f"[{label}]({url})" if url else label

            code = (
                    match.group("bracket_code")
                    or match.group("inline_code")
                    or match.group("code")
            )
            url = self.course_links.get(code.upper())

            if not url:
                # The model bracketed a code it has no link for: show the code, not "[CP164]".
                return code if match.group("bracket_code") else match.group(0)

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