"""Shared matcher contract: the MaskingState matchers mutate and the EntityMatcher protocol."""
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from backend.domain.entities.question import EntityLookup, EntityMap, EntityType


@dataclass
class MaskingState:
    """The extractor's working copy of a question: matchers progressively mask it and record entities.

    Matchers run in order and each sees the previous ones' masks, so an earlier matcher wins
    a span (a valid course code "BA101" is never re-read as a room).
    """
    text: str
    entities: EntityMap = field(default_factory=dict)
    counters: Counter = field(default_factory=Counter)

    def next_mask(self, entity_type: EntityType) -> str:
        """'[COURSE1]', '[COURSE2]', ... numbered per entity type."""
        self.counters[entity_type] += 1
        return f"[{entity_type.value.upper()}{self.counters[entity_type]}]"


class EntityMatcher(Protocol):
    def apply(self, state: MaskingState, lookup: EntityLookup) -> None:
        """Mask this matcher's entity kind in `state.text` and record each one in `state.entities`."""
        ...
