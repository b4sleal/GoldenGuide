"""Resolve the scraper's one-based @@n@@ link placeholders in Academic Calendar Markdown into real URLs."""
import re
from collections.abc import Sequence
from urllib.parse import urlparse


class AcademicLinkResolver:
    """Resolve one-based scraper links in Academic Calendar Markdown."""

    LINK_PATTERN = re.compile(
        r"\]\s*\\?\(\s*@@(\d+)@@\s*\\?\)"
    )

    @staticmethod
    def _valid_url(value: object) -> bool:
        if not isinstance(value, str):
            return False

        parsed = urlparse(value.strip())

        return (
                parsed.scheme in {"https", "http"}
                and bool(parsed.netloc)
        )

    @classmethod
    def resolve(
            cls,
            content: str | None,
            external_links: Sequence[str] | None,
    ) -> str:
        """`content` with each valid placeholder linked; an invalid or missing link keeps only its label."""
        links = external_links or []

        def replace(match: re.Match) -> str:
            # Scraper placeholders are ONE-based.
            index = int(match.group(1)) - 1

            if index < 0 or index >= len(links):
                return "]"

            url = links[index]

            if not cls._valid_url(url):
                return "]"

            return f"]({url.strip()})"

        return cls.LINK_PATTERN.sub(
            replace,
            content or "",
            )
