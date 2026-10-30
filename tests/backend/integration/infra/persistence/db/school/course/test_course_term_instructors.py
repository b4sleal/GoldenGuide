"""Instructor filtering and the instructor catalog, against real PostgreSQL on the migrated schema."""
import pytest

from backend.domain.entities.wlu.loris_registration import CourseFaculty
from backend.domain.ports.repositories.filters import CourseTermFilter
from tests.backend.integration.infra.persistence.db.school.course.helpers import matching_crns, seed, section


def person(banner_id, name, primary=True):
    return {"bannerId": banner_id, "displayName": name, "emailAddress": f"{banner_id}@wlu.ca", "primaryIndicator": primary}


@pytest.fixture
async def db(session):
    await seed(session, [
        section("1", faculty=[person("100", "Heider Ali")]),
        section("2", faculty=[person("101", "Ali Hosseini"), person("100", "Heider Ali", primary=False)]),  # Co-taught.
        section("3", faculty=[person("102", "Alison Blay-Palmer")]),
        section("4", faculty=[]),                                                                          # TBA.
        section("6", faculty=[{"bannerId": None, "displayName": "No Identity"}]),
    ])
    return session


async def test_instructor_matches_sections_they_teach_including_co_taught(db):
    assert await matching_crns(db, CourseTermFilter(instructor_ids=["100"])) == {"1", "2"}


async def test_several_instructors_use_or(db):
    assert await matching_crns(db, CourseTermFilter(instructor_ids=["101", "102"])) == {"2", "3"}


async def test_unknown_instructor_matches_nothing(db):
    assert await matching_crns(db, CourseTermFilter(instructor_ids=["999"])) == set()


async def test_fetch_instructors_lists_each_identity_once(db, course_terms):
    # One per bannerId; TBA sections and identity-less entries contribute nothing.
    assert await course_terms.fetch_instructors() == [
        CourseFaculty(bannerId="100", displayName="Heider Ali"),
        CourseFaculty(bannerId="101", displayName="Ali Hosseini"),
        CourseFaculty(bannerId="102", displayName="Alison Blay-Palmer"),
    ]
