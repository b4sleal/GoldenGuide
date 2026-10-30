"""Course-code matcher: "CP104", "cp 104" and lexicon aliases ("comp sci 104"), kept only if in the catalog."""
import re

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.domain.entities.question import CourseEntity, EntityLookup, EntityType
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.loris_registration import LexiconEntityType


class CourseCodeMatcher:
    """Course references ("CP104", "cp 104", "comp sci 104") that exist in the course catalog."""

    def __init__(self, lexicon_resolver: WluLexiconResolver):
        self.lexicon_resolver = lexicon_resolver

        # Two-letter subject code + number: "CP104", "cp 104".
        self.standard_course_pattern = re.compile(r'\b([a-zA-Z]{2})\s*(\d{3}[a-zA-Z]?)\b')
        self.alias_course_pattern = self._build_alias_course_regex()

    def _build_alias_course_regex(self) -> re.Pattern:
        """Subject alias + number ("comp sci 104"), built once from the lexicon."""
        subject_aliases = self.lexicon_resolver.get_aliases(LexiconEntityType.SUBJECT)
        if not subject_aliases:
            return re.compile(r'(?!x)x')  # Never matches: no aliases configured.

        # Longest aliases first, so "computer science" wins over "science".
        aliases = sorted(subject_aliases, key=len, reverse=True)
        escaped_aliases = [re.escape(a) for a in aliases]
        pattern_str = rf"\b({'|'.join(escaped_aliases)})\s+(\d{{3}}[a-zA-Z]?)\b"
        return re.compile(pattern_str, re.IGNORECASE)

    def apply(self, state: MaskingState, lookup: EntityLookup) -> None:
        # Aliases first: "comp sci 104" must be claimed whole before "sci 104" could look like a code.
        valid_courses = set(lookup.courses)

        for match in self.alias_course_pattern.finditer(state.text):
            raw_string = match.group(0)
            matched_alias = match.group(1).lower()
            course_number = match.group(2).upper()

            canonical_name = self.lexicon_resolver.resolve_subject(matched_alias)
            subject_code = (
                    self.lexicon_resolver.resolve_course_code(matched_alias)
                    # Fallback for subjects missing from the lexicon
                    or lookup.subjects.get(canonical_name)
            )

            if subject_code:
                self._mask(state, raw_string, f"{subject_code}{course_number}", valid_courses)

        for match in self.standard_course_pattern.finditer(state.text):
            normalized_code = f"{match.group(1).upper()}{match.group(2).upper()}"
            self._mask(state, match.group(0), normalized_code, valid_courses)

    @staticmethod
    def _mask(state: MaskingState, raw_string: str, normalized_code: str, valid_courses: set[str]) -> None:
        """Mask the first occurrence of `raw_string`, only if the code exists (unknown codes are not courses)."""
        if normalized_code not in valid_courses:
            return
        mask = state.next_mask(EntityType.COURSE)
        pattern = re.compile(re.escape(raw_string), re.IGNORECASE)
        state.text = pattern.sub(mask, state.text, count=1)
        state.entities[mask] = CourseEntity(raw=raw_string, normalized=normalized_code)
