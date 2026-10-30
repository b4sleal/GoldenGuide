"""Exact phrase lookup for matchers whose vocabulary comes from data (rooms, instructors).

A phrase is one or more adjacent words; it matches only if its key is in an index built from the
cached database values. Nothing here recognizes shapes: unknown text is never an entity.
"""
import itertools
import re
from collections.abc import Callable, Mapping, Sequence

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.domain.entities.question import EntityType, ExtractedEntity

type Span[V] = tuple[int, int, V]

WHITESPACE = re.compile(r"\s+")


def find_phrases[V](
        text: str,
        index: Mapping[str, V],
        *,
        word: re.Pattern,
        key: Callable[[Sequence[str]], str],
        max_words: int,
        separator: re.Pattern = WHITESPACE,
) -> list[Span[V]]:
    """(start, end, value) for each indexed phrase, left to right, longest phrase first at each position.

    Words inside earlier masks ("[COURSE1]") are skipped, and a phrase's words must be separated by
    exactly `separator` (default whitespace: "SC N3021" is one phrase, "SC, N3021" is not).
    """
    words = [match for match in word.finditer(text) if text[match.start() - 1:match.start()] != "["]
    found: list[Span[V]] = []

    position = 0
    while position < len(words):
        for width in range(min(max_words, len(words) - position), 0, -1):
            group = words[position:position + width]
            if not all(separator.fullmatch(text[a.end():b.start()]) for a, b in itertools.pairwise(group)):
                continue
            phrase = key([match.group(0) for match in group])
            if phrase in index:
                found.append((group[0].start(), group[-1].end(), index[phrase]))
                position += width
                break
        else:
            position += 1

    return found


def mask_spans[V](
        state: MaskingState,
        spans: list[Span[V]],
        entity_type: EntityType,
        entity: Callable[[str, V], ExtractedEntity],
) -> None:
    """Replace each span with a mask and record `entity(raw_text, value)` under it.

    Masks are numbered left to right; text is replaced right to left so earlier offsets stay valid.
    """
    masks = []
    for start, end, value in spans:
        mask = state.next_mask(entity_type)
        state.entities[mask] = entity(state.text[start:end], value)
        masks.append((start, end, mask))

    for start, end, mask in reversed(masks):
        state.text = state.text[:start] + mask + state.text[end:]
