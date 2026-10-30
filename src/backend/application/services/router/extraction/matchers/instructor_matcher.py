"""Instructor matcher: exact full-name lookup against the instructors teaching LORIS sections."""
import re
from collections import defaultdict
from collections.abc import Sequence

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.application.services.router.extraction.matchers.phrase_index import (
    find_phrases,
    mask_spans,
)
from backend.domain.entities.question import EntityLookup, EntityType, InstructorEntity
from backend.domain.entities.wlu.loris_registration import CourseFaculty

# Names split on punctuation, so "Blay-Palmer" and "blay palmer" read the same.
NAME_WORD = re.compile(r"[A-Za-z0-9]+")
NAME_SEPARATOR = re.compile(r"[\s'-]+")
MAX_NAME_WORDS = 5


def name_key(words: Sequence[str]) -> str:
    """Index key of a name: case-folded words joined by single spaces."""
    return " ".join(word.casefold() for word in words)


def build_instructor_index(instructors: list[CourseFaculty]) -> dict[str, list[CourseFaculty]]:
    """Full display name -> instructors. Full names only: a surname alone ("Ali", "Young", "Wood")
    is ambiguous between people and collides with ordinary words."""
    index: dict[str, list[CourseFaculty]] = defaultdict(list)
    for instructor in instructors:
        words = NAME_WORD.findall(instructor.displayName or "")
        if instructor.bannerId and 2 <= len(words) <= MAX_NAME_WORDS:
            index[name_key(words)].append(instructor)
    return dict(index)


class InstructorMatcher:
    """Instructors who teach a LORIS section ("Heider Ali", "heider ali"), by exact full-name lookup."""

    def apply(self, state: MaskingState, lookup: EntityLookup) -> None:
        index = build_instructor_index(lookup.instructors)
        if not index:
            return

        spans = find_phrases(
            state.text, index, word=NAME_WORD, key=name_key, max_words=MAX_NAME_WORDS, separator=NAME_SEPARATOR,
        )
        mask_spans(state, spans, EntityType.INSTRUCTOR, lambda raw, instructors: InstructorEntity(
            raw=raw,
            canonical=" / ".join(instructor.displayName for instructor in instructors),
            # Identity and name only: contact details stay out of prompts and logs.
            instructors=[
                CourseFaculty(bannerId=instructor.bannerId, displayName=instructor.displayName)
                for instructor in instructors
            ],
        ))
