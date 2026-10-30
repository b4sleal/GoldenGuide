"""Fuzzy department hints for misspelled or truncated names; recorded for the planner, never masked."""
import re

from rapidfuzz import fuzz, process

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.domain.entities.question import (
    DisciplineEntity,
    EntityLookup,
    EntityMatch,
    EntityType,
)
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from backend.domain.entities.wlu.loris_registration import LexiconEntityType

HINT_WORD = re.compile(r"[a-zA-Z]{4,}")
MAX_WORDS = 30
MAX_HINTS = 3
# rapidfuzz ratio (0-100). A candidate needs CANDIDATE_SCORE to be considered and CONFIDENT_SCORE to be
# kept, unless it is a prefix completion ("psycho" -> "psychology").
CANDIDATE_SCORE = 73
CONFIDENT_SCORE = 85
MIN_PREFIX_LENGTH = 5


class DepartmentHintMatcher:
    """Fuzzy department guesses ("psycho" -> Psychology), recorded as hints, never masked.

    The lexical resolver provides optional hypotheses, never a forced rewrite. It tests short
    spans, not the complete student sentence, and the router LLM decides whether they are relevant.
    Hints carry EntityMatch.FUZZY_HINT so deterministic consumers ignore them.
    """

    def __init__(self, lexicon_resolver: WluLexiconResolver):
        # Alias -> canonical department, built once: the lexicon is fixed configuration.
        self.aliases = {
            alias: lexicon_resolver.resolve(LexiconEntityType.DEPARTMENT, alias)
            for alias in lexicon_resolver.get_aliases(LexiconEntityType.DEPARTMENT)
        }

    def apply(self, state: MaskingState, lookup: EntityLookup) -> None:
        aliases = self.aliases
        already_matched = {
            entity.canonical for entity in state.entities.values() if isinstance(entity, DisciplineEntity)
        }
        seen_hints = set()
        # Limit candidate work and prevent free-form fuzzy matches becoming SQL.
        words = HINT_WORD.findall(state.text.casefold())[:MAX_WORDS]
        for word in words:
            choices = process.extract(
                word, aliases.keys(), scorer=fuzz.ratio,
                score_cutoff=CANDIDATE_SCORE, limit=3,
            )
            for alias, score, _ in choices:
                canonical = aliases[alias]
                if not canonical or canonical in already_matched or canonical in seen_hints:
                    continue
                # Prefix completions support student truncations such as
                # "psycho" -> "Psychology" without guessing intent.
                if score < CONFIDENT_SCORE and not (
                        alias.startswith(word) and len(word) >= MIN_PREFIX_LENGTH
                ):
                    continue
                state.entities[state.next_mask(EntityType.DEPARTMENT)] = DisciplineEntity(
                    type=EntityType.DEPARTMENT,
                    raw=word,
                    canonical=canonical,
                    match=EntityMatch.FUZZY_HINT,
                )
                seen_hints.add(canonical)
                break
            if len(seen_hints) >= MAX_HINTS:
                break
