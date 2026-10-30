"""Meeting-room matcher: exact lookup of LORIS room identifiers as students write them."""
import re
from collections import defaultdict

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.application.services.router.extraction.matchers.phrase_index import (
    find_phrases,
    mask_spans,
)
from backend.domain.entities.question import EntityLookup, EntityType, RoomEntity
from backend.domain.entities.wlu.loris_registration import MeetingRoom

# Room words keep hyphens ("AC1-59"); two words join without a space ("LH 1009" -> "LH1009").
ROOM_WORD = re.compile(r"[A-Za-z0-9-]+")


def room_aliases(room: MeetingRoom) -> set[str]:
    """How students write a room: as stored ("LH1009", "N3021") or building-prefixed ("SCN3021",
    also "SC N3021" via two-word lookup). Only identifiers containing a digit are matchable: plain
    words ("GYM", "VIRTUAL") collide with ordinary English and with other filters (delivery)."""
    aliases = {room.room.upper()}
    if room.building and not room.room.upper().startswith(room.building.upper()):
        aliases.add(f"{room.building}{room.room}".upper())
    return {alias for alias in aliases if any(char.isdigit() for char in alias)}


def room_label(room: MeetingRoom) -> str:
    """Readable room name: 'SC N3021', or the room alone when it already starts with its building."""
    if room.building and not room.room.upper().startswith(room.building.upper()):
        return f"{room.building} {room.room}"
    return room.room


def build_room_index(rooms: list[MeetingRoom]) -> dict[str, list[MeetingRoom]]:
    """Alias -> rooms. Usually one room; a list keeps genuinely shared names explicit."""
    index: dict[str, list[MeetingRoom]] = defaultdict(list)
    for room in rooms:
        for alias in room_aliases(room):
            index[alias].append(room)
    return dict(index)


class RoomMatcher:
    """Meeting rooms that exist in LORIS ("LH1009", "lh 1009", "SC N3021"), by exact lookup."""

    def apply(self, state: MaskingState, lookup: EntityLookup) -> None:
        index = build_room_index(lookup.rooms)
        if not index:
            return

        spans = find_phrases(
            state.text, index, word=ROOM_WORD, key=lambda words: "".join(words).upper(), max_words=2,
        )
        mask_spans(state, spans, EntityType.ROOM, lambda raw, rooms: RoomEntity(
            raw=raw,
            canonical=" / ".join(room_label(room) for room in rooms),
            rooms=rooms,
        ))
