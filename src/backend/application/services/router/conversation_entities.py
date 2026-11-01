"""Entities carried between the turns of a conversation, so "is it offered in winter?" can mean CP264.

Carried entities get their own masks ("[EARLIER_COURSE1]"), so they never collide with the current
question's masks and the router can tell where each one came from. They are offered to the router
like any recognized entity, and the plan validators still reject anything outside the two sets.
"""
from collections import Counter

from backend.domain.entities.question import EntityMap, ExtractedEntity

EARLIER_MASK_PREFIX = "EARLIER_"


def _identity(entity: ExtractedEntity) -> dict:
    # The same course or program, however the student wrote it.
    return entity.model_dump(exclude={"raw"})


def relabel_earlier(earlier: EntityMap, current: EntityMap) -> EntityMap:
    """Earlier entities under EARLIER_ masks, leaving out any the current question already names."""
    named_now = [_identity(entity) for entity in current.values()]
    counts: Counter[str] = Counter()
    relabelled: EntityMap = {}
    for entity in earlier.values():
        if _identity(entity) in named_now:
            continue
        kind = entity.type.value.upper()
        counts[kind] += 1
        relabelled[f"[{EARLIER_MASK_PREFIX}{kind}{counts[kind]}]"] = entity
    return relabelled


def entities_to_carry(current: EntityMap, earlier: EntityMap, referenced: set[str]) -> EntityMap:
    """What the next turn may refer back to: this question's entities and the earlier ones it used.

    Earlier entities the plan did not use are dropped, so a change of topic ends the old context.
    """
    return current | {mask: entity for mask, entity in earlier.items() if mask in referenced}
