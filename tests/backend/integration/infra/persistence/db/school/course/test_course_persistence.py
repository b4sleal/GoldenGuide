"""Calendar persistence rules, verified through repository methods on the migrated test DB."""

import pytest

from backend.domain.entities.wlu.course import (
    CourseCreate,
    CourseMetadata,
    CourseRead,
    CourseUpdate,
)
from backend.domain.ports.repositories.filters import CourseFilter
from backend.domain.ports.repositories.school.query_types import CoursePageParams
from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps
from backend.infra.persistence.db.school.base.course_page_repo import (
    SqlCourseRepository,
)


@pytest.fixture
def courses(session):
    return SqlCourseRepository(session, PostgresDialectOps())


def course(**changes) -> CourseCreate:
    return CourseCreate(
        **{
            "academic_year": "2026/2027",
            "institution": "WLU",
            "subject": "Computer Science",
            "subject_code": "CP",
            "course_number": "104",
            "campus": "Waterloo",
            "title": "Introduction to Programming",
            "description": "Calendar description",
            "metadata_json": CourseMetadata(),
            **changes,
        },
    )


async def read(courses) -> CourseRead:
    [result] = await courses.fetch_courses(
        CoursePageParams(), CourseFilter(subject_code="CP", course_number="104")
    )
    assert isinstance(
        result, CourseRead
    )  # ORM objects must not cross the repository boundary.
    return result


async def test_repeated_upsert_preserves_identity_without_duplicate_rows(courses):
    first = await courses.upsert_course(course())
    assert await courses.upsert_course(course()) == first
    assert await courses.count_courses() == 1
    assert (await read(courses)).id == first


async def test_insert_only_import_cannot_overwrite_calendar_data(courses):
    original_id = await courses.upsert_course(course())

    assert (
        await courses.insert_courses([course(title="LORIS title", description=None)])
        == []
    )
    stored = await read(courses)
    assert stored.id == original_id
    assert stored.title == "Introduction to Programming"
    assert stored.description == "Calendar description"


@pytest.mark.parametrize(
    "changes,dirty",
    [
        ({}, False),
        ({"title": "Revised title"}, True),
        ({"description": None}, True),
        ({"prereq": "CP103"}, True),
        ({"calendar_url": "https://example.edu/revised"}, False),
        ({"content_hash": "new-source-hash"}, False),
    ],
    ids=["unchanged", "title", "text-removed", "prerequisite", "url-only", "hash-only"],
)
async def test_only_embedding_content_changes_invalidate_an_indexed_course(
    courses, changes, dirty
):
    course_id = await courses.upsert_course(course())
    # Simulate successful indexing through the public repository, then re-import the source.
    await courses.update_courses([course_id], CourseUpdate(needs_embedding=False))

    await courses.upsert_course(course(**changes))

    stored = await read(courses)
    assert stored.needs_embedding is dirty
    for field, expected in changes.items():
        assert getattr(stored, field) == expected


async def test_reimport_cannot_clear_an_existing_embedding_backlog(courses):
    await courses.upsert_course(course())

    await courses.upsert_course(course(needs_embedding=False))

    assert (await read(courses)).needs_embedding is True


async def test_failed_transaction_rolls_back_persisted_changes(courses, session):
    course_id = await courses.upsert_course(course())

    # A batch failure must not leave half of its changes visible to the next batch.
    with pytest.raises(RuntimeError, match="batch failed"):
        async with session.begin_nested():
            await courses.upsert_course(course(title="Uncommitted title"))
            raise RuntimeError("batch failed")

    stored = await read(courses)
    assert stored.id == course_id
    assert stored.title == "Introduction to Programming"


async def test_empty_imports_are_safe_noops(courses):
    assert await courses.upsert_courses([]) == []
    assert await courses.insert_courses([]) == []
    assert await courses.count_courses() == 0
