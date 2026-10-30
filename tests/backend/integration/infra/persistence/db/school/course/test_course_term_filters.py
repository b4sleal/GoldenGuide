"""Meeting-day filters, against real PostgreSQL on the migrated schema."""
import pytest

from backend.domain.ports.repositories.filters import CourseTermFilter
from tests.backend.integration.infra.persistence.db.school.course.helpers import matching_crns, seed, section


@pytest.fixture
async def db(session):
    await seed(session, [
        section("1", meetings=[{"monday": True, "wednesday": True, "beginTime": "1000", "endTime": "1120"}]),
        section("2", meetings=[{"tuesday": True, "thursday": True, "beginTime": "1300", "endTime": "1420"}]),
        section("3", meetings=[{"monday": True, "beginTime": "0900"}, {"friday": True, "beginTime": "1500"}]),
        section("4", meetings=[]),
    ])
    return session


async def test_preferred_day_matches_any_meeting(db):
    assert await matching_crns(db, CourseTermFilter(day_preference=["monday"])) == {"1", "3"}


async def test_excluded_day_checks_every_meeting(db):
    assert await matching_crns(db, CourseTermFilter(day_exclusion=["friday"])) == {"1", "2"}


async def test_multiple_preferences_use_or(db):
    assert await matching_crns(db, CourseTermFilter(day_preference=["monday", "tuesday"])) == {"1", "2", "3"}


async def test_preferences_and_exclusions_combine(db):
    assert await matching_crns(db, CourseTermFilter(day_preference=["monday"], day_exclusion=["friday"])) == {"1"}


async def test_excluding_a_day_keeps_sections_without_it(db):
    assert await matching_crns(db, CourseTermFilter(day_exclusion=["monday"])) == {"2"}


async def test_sections_without_meetings_never_match(db):
    # A missing schedule cannot be treated as conflict-free.
    assert await matching_crns(db, CourseTermFilter(day_exclusion=["sunday"])) == {"1", "2", "3"}
