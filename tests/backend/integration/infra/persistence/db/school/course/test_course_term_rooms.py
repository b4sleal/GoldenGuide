"""Room filtering and the room catalog, against real PostgreSQL on the migrated schema."""
import pytest

from backend.domain.entities.wlu.loris_registration import MeetingRoom
from backend.domain.ports.repositories.filters import CourseTermFilter
from tests.backend.integration.infra.persistence.db.school.course.helpers import matching_crns, seed, section

LH1009 = MeetingRoom(building="LH", room="LH1009")
N3021 = MeetingRoom(building="SC", room="N3021")


def meeting(day, building, room):
    return {day: True, "building": building, "room": room}


@pytest.fixture
async def db(session):
    await seed(session, [
        section("1", meetings=[meeting("friday", "LH", "LH1009")]),
        section("2", meetings=[meeting("monday", "LH", "LH1009"), meeting("friday", "SC", "N3021")]),  # LH1009 only Monday.
        section("3", meetings=[meeting("friday", "SC", "N3021")]),
        section("4", meetings=[meeting("tuesday", "US", "GYM")]),          # Same room name, different building.
        section("5", meetings=[meeting("tuesday", "AC", "GYM")]),
        section("6", meetings=[meeting("wednesday", None, "P118")]),       # No building recorded.
        section("7", meetings=[meeting("monday", "LH", None)]),            # Room TBA.
        section("8", meetings=[meeting("monday", "LH", "")]),
        section("9", meetings=[]),
    ])
    return session


async def test_room_matches_any_meeting(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[LH1009])) == {"1", "2"}


async def test_room_and_day_must_be_the_same_meeting(db):
    # Section 2 meets in LH1009 on Monday and elsewhere on Friday: not "LH1009 on Friday".
    assert await matching_crns(db, CourseTermFilter(rooms=[LH1009], day_preference=["friday"])) == {"1"}


async def test_room_with_any_of_several_days(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[LH1009], day_preference=["monday", "friday"])) == {"1", "2"}


async def test_day_exclusion_still_applies_to_every_meeting(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[LH1009], day_exclusion=["friday"])) == set()
    assert await matching_crns(db, CourseTermFilter(rooms=[LH1009], day_exclusion=["monday"])) == {"1"}


async def test_building_is_part_of_room_identity(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[MeetingRoom(building="US", room="GYM")])) == {"4"}


async def test_room_without_building(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[MeetingRoom(building=None, room="P118")])) == {"6"}


async def test_several_rooms_use_or(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[LH1009, N3021])) == {"1", "2", "3"}


async def test_unknown_room_matches_nothing(db):
    assert await matching_crns(db, CourseTermFilter(rooms=[MeetingRoom(building="LH", room="LH9999")])) == set()


async def test_fetch_meeting_rooms_lists_each_physical_room_once(db, course_terms):
    # Distinct (building, room); TBA/empty rooms and sections without meetings contribute nothing.
    assert await course_terms.fetch_meeting_rooms() == [
        MeetingRoom(building="AC", room="GYM"),
        MeetingRoom(building="LH", room="LH1009"),
        MeetingRoom(building="SC", room="N3021"),
        MeetingRoom(building="US", room="GYM"),
        MeetingRoom(building=None, room="P118"),
    ]
