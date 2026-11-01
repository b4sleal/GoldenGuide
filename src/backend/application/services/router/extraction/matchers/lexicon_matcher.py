"""Faculty, department and subject matcher: exact names and aliases from the WLU lexicon and the catalog."""
import re
from dataclasses import dataclass
from functools import lru_cache

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.domain.entities.question import DisciplineEntity, EntityLookup, EntityType
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.loris_registration import LexiconEntityType

# Lexicon sections this matcher sweeps, and the entity each becomes. Subjects and departments carry a
# course subject code; faculties do not.
SWEPT_SECTIONS = {
    LexiconEntityType.FACULTY: EntityType.FACULTY,
    LexiconEntityType.DEPARTMENT: EntityType.DEPARTMENT,
    LexiconEntityType.SUBJECT: EntityType.SUBJECT,
}
CODED_TYPES = {EntityType.DEPARTMENT, EntityType.SUBJECT}


@dataclass(frozen=True)
class PoolTerm:
    term: str
    canonical: str
    entity_type: EntityType
    # Subject codes ("IT", "CP") match only as written in capitals: in lower case they are ordinary
    # words ("is it offered?" is not Italian). Names and aliases match in any case.
    case_sensitive: bool = False


@lru_cache(maxsize=8192)
def whole_word(term: str, case_sensitive: bool) -> re.Pattern:
    """Whole-word pattern, compiled once per term (lexicon aliases and catalog subjects are a few
    thousand fixed strings, so the cache holds them all)."""
    return re.compile(rf'\b{re.escape(term)}\b', 0 if case_sensitive else re.IGNORECASE)


class LexiconEntityMatcher:
    """Exact faculty, department and subject names and aliases, longest first.

    One global sweep prevents cross-contamination: "Computer Science" (subject) is extracted
    before "Science" (faculty) can claim part of it.
    """

    def __init__(self, lexicon_resolver: WluLexiconResolver):
        self.lexicon_resolver = lexicon_resolver
        # The lexicon is fixed configuration: build its part of the pool once, not per question.
        self.lexicon_pool = [
            self._pool_term(section, alias, entity_type)
            for section, entity_type in SWEPT_SECTIONS.items()
            for alias in lexicon_resolver.get_aliases(section)
        ]

    def _pool_term(self, section: LexiconEntityType, alias: str, entity_type: EntityType) -> PoolTerm:
        canonical = self.lexicon_resolver.resolve(section, alias)
        if alias in self.lexicon_resolver.course_codes(section):
            return PoolTerm(alias.upper(), canonical, entity_type, case_sensitive=True)
        return PoolTerm(alias.lower(), canonical, entity_type)

    def apply(self, state: MaskingState, lookup: EntityLookup) -> None:
        # Lexicon aliases, plus catalog subject names (subjects missing from the lexicon), which come from data.
        pool = self.lexicon_pool + [PoolTerm(name.lower(), name, EntityType.SUBJECT) for name in lookup.subjects]

        # Longest first. Stable sort: for equal lengths, faculty < department < subject (insertion order).
        pool.sort(key=lambda item: len(item.term), reverse=True)

        for item in pool:
            pattern = whole_word(item.term, item.case_sensitive)
            if not pattern.search(state.text):
                continue

            mask = state.next_mask(item.entity_type)
            state.text = pattern.sub(mask, state.text)
            state.entities[mask] = DisciplineEntity(
                type=item.entity_type,
                raw=item.term,
                canonical=item.canonical,
                code=(
                    self.lexicon_resolver.resolve_course_code(item.canonical)
                    or lookup.subjects.get(item.canonical)
                ) if item.entity_type in CODED_TYPES else None,
            )
