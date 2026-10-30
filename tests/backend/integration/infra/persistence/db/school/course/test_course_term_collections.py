"""Course-term child collections round-trip through upsert, update and fetch on real PostgreSQL."""
from pydantic import BaseModel

from backend.domain.entities.wlu.loris_registration import (
    CourseFaculty,
    CourseMeetingTime,
    CourseTermRead,
    CourseTermUpdate,
)
from backend.domain.ports.repositories.filters import CourseTermFilter
from backend.domain.ports.repositories.school.query_types import CourseTermParams
from tests.backend.integration.infra.persistence.db.school.course.helpers import TERM_CODE, seed, section

LECTURE = {"monday": True, "beginTime": "1000", "building": "LH", "room": "LH1009"}
LAB = {"thursday": True, "beginTime": "1400", "building": "SC", "room": "N3021"}
ALI = {"bannerId": "100", "displayName": "Heider Ali", "primaryIndicator": True}
TA = {"bannerId": "200", "displayName": "Lab TA", "primaryIndicator": False}


class TitleOnly(BaseModel):
    crn: str
    title: str | None


async def fetch_one(course_terms, view_model=CourseTermRead):
    [term] = await course_terms.fetch_course_terms(
        CourseTermParams(limit=10), CourseTermFilter(term_code=TERM_CODE), view_model=view_model,
    )
    return term


async def test_collections_and_columns_are_stored_and_read_back_in_order(session, course_terms):
    await seed(session, [section(
        "1", meetings=[LECTURE, LAB], faculty=[ALI, TA], credit_hours=0.5, seats_available=3, wait_available=0,
    )])

    term = await fetch_one(course_terms)

    assert term.meetings == [CourseMeetingTime(**LECTURE), CourseMeetingTime(**LAB)]
    assert term.faculty == [CourseFaculty(**ALI), CourseFaculty(**TA)]
    assert (term.credit_hours, term.seats_available, term.wait_available) == (0.5, 3, 0)


async def test_reupsert_replaces_collections_instead_of_appending(session, course_terms):
    await seed(session, [section("1", meetings=[LECTURE, LAB], faculty=[ALI, TA])])
    await seed(session, [section("1", meetings=[LAB], faculty=[])])

    term = await fetch_one(course_terms)

    assert term.meetings == [CourseMeetingTime(**LAB)]
    assert term.faculty == []


async def test_update_replaces_only_the_collections_it_sets(session, course_terms):
    await seed(session, [section("1", meetings=[LECTURE], faculty=[ALI])])
    term = await fetch_one(course_terms)

    await course_terms.update_course_terms([term.id], CourseTermUpdate(meetings=[LAB], needs_embedding=False))
    updated = await fetch_one(course_terms)

    assert updated.meetings == [CourseMeetingTime(**LAB)]
    assert updated.faculty == [CourseFaculty(**ALI)]
    assert updated.needs_embedding is False


async def test_views_without_collections_still_fetch(session, course_terms):
    await seed(session, [section("1", meetings=[LECTURE], title="Data Structures")])

    assert await fetch_one(course_terms, view_model=TitleOnly) == TitleOnly(crn="1", title="Data Structures")
