import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from backend.application.services.router.extraction.entity_lookup_cache import (
    EntityLookupCache,
)
from backend.domain.entities.question import EntityLookup
from backend.domain.entities.wlu.loris_registration import CourseFaculty, MeetingRoom
from tests.backend.unit.application.services.router.factories import (
    INSTITUTION,
    ROUTER_SETTINGS,
)


@pytest.fixture
def setup_service():
    db = Mock()
    cache = Mock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()

    repos = Mock()
    repos.courses.fetch_courses = AsyncMock()
    repos.wlu_pages.fetch_records = AsyncMock()
    repos.course_terms.fetch_meeting_rooms = AsyncMock(return_value=[])
    repos.course_terms.fetch_instructors = AsyncMock(return_value=[])

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=repos)
    context.__aexit__ = AsyncMock(return_value=None)
    db.start.return_value = context

    settings = ROUTER_SETTINGS.entity_lookup_cache.model_copy(update={"batch_size": 2})
    service = EntityLookupCache(db, cache, INSTITUTION, settings)

    return service, repos, cache


@pytest.mark.asyncio
async def test_refresh_cache_paginates_and_deduplicates(setup_service):
    service, repos, cache = setup_service

    repos.courses.fetch_courses.side_effect = [
        [
            Mock(subject_code="CP", course_number="104", subject="Computer Science"),
            Mock(subject_code="CP", course_number="213", subject="Computer Science"),
        ],
        [
            Mock(subject_code="CP", course_number="104", subject="Computer Science"),
        ],
    ]

    repos.wlu_pages.fetch_records.side_effect = [
        [Mock(title="Computer Science"), Mock(title="Mathematics")],
        [Mock(title="Computer Science")],
    ]

    repos.course_terms.fetch_meeting_rooms.return_value = [
        MeetingRoom(building="LH", room="LH1009"),
        MeetingRoom(building="SC", room="N3021"),
    ]
    repos.course_terms.fetch_instructors.return_value = [
        CourseFaculty(bannerId="100", displayName="Heider Ali", emailAddress="x@wlu.ca", primaryIndicator=True),
    ]

    result = await service.refresh_cache()

    assert result == EntityLookup(
        courses=["CP104", "CP213"],
        subjects={"Computer Science": "CP"},
        programs=["Computer Science", "Mathematics"],
        rooms=[MeetingRoom(building="LH", room="LH1009"), MeetingRoom(building="SC", room="N3021")],
        # Only identity and name are cached: no email addresses in the shared cache.
        instructors=[CourseFaculty(bannerId="100", displayName="Heider Ali")],
    )

    assert repos.courses.fetch_courses.await_count == 2
    assert repos.wlu_pages.fetch_records.await_count == 2

    cache.set.assert_awaited_once()
    cached = cache.set.await_args.args[1]
    assert EntityLookup.model_validate_json(cached) == result
    assert b"emailAddress" not in cached and b"null" not in cached


@pytest.mark.asyncio
async def test_cache_hit_skips_database(setup_service):
    service, repos, cache = setup_service

    expected = EntityLookup(
        courses=["CP104"],
        subjects={"Computer Science": "CP"},
        rooms=[MeetingRoom(building="LH", room="LH1009")],
    )

    cache.get.return_value = expected.model_dump_json().encode()

    result = await service.get_lookup_data()

    assert result == expected
    repos.courses.fetch_courses.assert_not_awaited()
    repos.wlu_pages.fetch_records.assert_not_awaited()
    repos.course_terms.fetch_meeting_rooms.assert_not_awaited()


@pytest.mark.asyncio
async def test_invalid_cache_refreshes(setup_service):
    service, repos, cache = setup_service

    cache.get.return_value = b"invalid-json"
    repos.courses.fetch_courses.return_value = []
    repos.wlu_pages.fetch_records.return_value = []

    result = await service.get_lookup_data()

    assert result == EntityLookup()

    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_database_failure_does_not_overwrite_cache(setup_service):
    service, repos, cache = setup_service

    repos.courses.fetch_courses.side_effect = RuntimeError("Database unavailable")

    with pytest.raises(RuntimeError, match="Database unavailable"):
        await service.refresh_cache()

    cache.set.assert_not_awaited()

@pytest.mark.asyncio
async def test_room_query_failure_does_not_overwrite_cache(setup_service):
    service, repos, cache = setup_service
    repos.courses.fetch_courses.return_value = []
    repos.wlu_pages.fetch_records.return_value = []
    repos.course_terms.fetch_meeting_rooms.side_effect = RuntimeError("Database unavailable")

    with pytest.raises(RuntimeError, match="Database unavailable"):
        await service.refresh_cache()

    cache.set.assert_not_awaited()


async def test_cache_outage_loads_from_database_once_then_reuses_that_copy(setup_service):
    # The cache is optional: Redis down must not fail questions or rescan the catalog for each one.
    service, repos, cache = setup_service
    cache.get.side_effect = ConnectionError("redis down")
    cache.set.side_effect = ConnectionError("redis down")
    repos.courses.fetch_courses.return_value = []
    repos.wlu_pages.fetch_records.return_value = []

    first = await service.get_lookup_data()
    second = await service.get_lookup_data()

    assert first == second == EntityLookup()
    assert repos.courses.fetch_courses.await_count == 1


def test_cache_key_is_versioned_past_the_roomless_payload(setup_service):
    # v2 entries have no "rooms"; reading one would silently disable room matching for a day.
    service, _, _ = setup_service
    assert service.cache_key not in {f"wlu:entity_lookup_lists:v{version}" for version in (2, 3, 4)}


async def test_concurrent_misses_reload_once(setup_service):
    # Single flight: when the entry expires, waiting questions reuse the one reload.
    service, repos, cache = setup_service
    stored = {}

    async def get(key):
        return stored.get(key)

    async def put(key, value, ttl=None):
        stored[key] = value

    cache.get.side_effect = get
    cache.set.side_effect = put
    repos.courses.fetch_courses.return_value = []
    repos.wlu_pages.fetch_records.return_value = []

    results = await asyncio.gather(*(service.get_lookup_data() for _ in range(5)))

    assert results == [EntityLookup()] * 5
    assert repos.courses.fetch_courses.await_count == 1
    cache.set.assert_awaited_once()
