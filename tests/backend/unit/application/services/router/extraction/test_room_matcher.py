import pytest

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.application.services.router.extraction.matchers.room_matcher import (
    RoomMatcher,
    build_room_index,
    room_aliases,
)
from backend.domain.entities.question import EntityLookup, RoomEntity
from backend.domain.entities.wlu.loris_registration import MeetingRoom

LH1009 = MeetingRoom(building="LH", room="LH1009")
N3021 = MeetingRoom(building="SC", room="N3021")


def match(text, lookup):
    state = MaskingState(text=text)
    RoomMatcher().apply(state, lookup)
    return state


@pytest.mark.parametrize("room, expected", [
    (MeetingRoom(building="LH", room="LH1009"), {"LH1009"}),            # Already prefixed.
    (MeetingRoom(building="SC", room="N3021"), {"N3021", "SCN3021"}),
    (MeetingRoom(building="ART", room="1C17"), {"1C17", "ART1C17"}),
    (MeetingRoom(building="US", room="GYM"), set()),                   # No digit: never matchable.
    (MeetingRoom(building=None, room="P118"), {"P118"}),
])
def test_room_aliases(room, expected):
    assert room_aliases(room) == expected


def test_index_keeps_shared_names_explicit():
    index = build_room_index([MeetingRoom(building="AA", room="101X"), MeetingRoom(building="BB", room="101X")])
    assert index["101X"] == [MeetingRoom(building="AA", room="101X"), MeetingRoom(building="BB", room="101X")]


@pytest.mark.parametrize("text", [
    "any courses in LH1009 on fridays",
    "any courses in lh1009 on fridays",
    "any courses in LH 1009 on fridays",     # Two words joined.
    "any courses in LH1009? on fridays",
])
def test_known_room_is_masked(text, lookup):
    state = match(text, lookup)

    assert "[ROOM1]" in state.text
    entity = state.entities["[ROOM1]"]
    assert isinstance(entity, RoomEntity)
    assert (entity.rooms, entity.canonical) == ([LH1009], "LH1009")


def test_building_prefixed_forms(lookup):
    for text in ("classes in SC N3021", "classes in SCN3021", "classes in N3021"):
        state = match(text, lookup)
        assert state.text == "classes in [ROOM1]", text
        assert state.entities["[ROOM1]"].rooms == [N3021]
        assert state.entities["[ROOM1]"].canonical == "SC N3021"


def test_unknown_room_shaped_words_are_not_rooms(lookup):
    # Rooms come from data, not from shape: LH9999 looks like a room but LORIS has none.
    state = match("anything in LH9999 or ZZ100 at 10am in 2027", lookup)
    assert state.entities == {}


def test_plain_word_rooms_are_not_matched(lookup):
    assert match("is there a gym class", lookup).entities == {}


def test_two_rooms_numbered_left_to_right(lookup):
    state = match("LH3060 or LH1009", lookup)

    assert state.text == "[ROOM1] or [ROOM2]"
    assert state.entities["[ROOM1]"].canonical == "LH3060"
    assert state.entities["[ROOM2]"].canonical == "LH1009"


def test_words_split_by_punctuation_are_not_joined(lookup):
    assert match("SC, N3021", lookup).entities["[ROOM1]"].raw == "N3021"


def test_existing_masks_are_never_read_as_words(lookup):
    lookup = lookup.model_copy(update={"rooms": [*lookup.rooms, MeetingRoom(building="X", room="COURSE1")]})
    state = match("[COURSE1] in LH1009", lookup)
    assert state.text == "[COURSE1] in [ROOM1]"


def test_no_rooms_in_lookup_is_a_no_op():
    state = match("in LH1009", EntityLookup())
    assert state.text == "in LH1009"
    assert state.entities == {}
