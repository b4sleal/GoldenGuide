"""The generic course repository owns entity rules and delegates only statement mechanics to its dialect."""
from backend.domain.entities.wlu.course import CourseCreate, CourseMetadata
from backend.infra.persistence.db.school.base.course_page_repo import SqlCourseRepository
from backend.infra.persistence.db.school.school_tables import Course


class RecordingDialect:
    """A SqlDialectOps double that records each call and returns fixed keys."""

    def __init__(self):
        self.calls = []

    async def upsert(self, session, **kwargs):
        self.calls.append(("upsert", session, kwargs))
        return [1]

    async def insert_ignore(self, session, **kwargs):
        self.calls.append(("insert_ignore", session, kwargs))
        return [2]


def course(**overrides) -> CourseCreate:
    fields = {
        "academic_year": "2026/2027", "institution": "wlu", "subject_code": "CP", "course_number": "220",
        "title": "Data Structures", "subject": "Computer Science", "campus": "Waterloo", "metadata_json": CourseMetadata(),
    }
    return CourseCreate(**(fields | overrides))


IDENTITY_COLUMNS = ["academic_year", "institution", "subject_code", "course_number"]


async def test_upsert_hands_prepared_course_rows_and_reembed_policy_to_the_dialect():
    dialect, session = RecordingDialect(), object()

    ids = await SqlCourseRepository(session, dialect).upsert_courses([course()])

    assert ids == [1]
    [(operation, used_session, call)] = dialect.calls
    assert (operation, used_session) == ("upsert", session)
    assert call["table"] is Course.__table__
    assert call["conflict_columns"] == IDENTITY_COLUMNS
    assert [row["title"] for row in call["rows"]] == ["Data Structures"]

    updates = call["build_updates"](Course.__table__.c, Course.__table__.c)
    assert "needs_embedding" in updates and "title" in updates


async def test_upsert_merges_duplicate_identities_before_reaching_the_dialect():
    dialect = RecordingDialect()

    await SqlCourseRepository(object(), dialect).upsert_courses([course(), course(title=None, notes="Lab")])

    [(_, _, call)] = dialect.calls
    assert len(call["rows"]) == 1


async def test_insert_courses_uses_insert_ignore_on_the_identity_columns():
    dialect = RecordingDialect()

    ids = await SqlCourseRepository(object(), dialect).insert_courses([course()])

    assert ids == [2]
    [(operation, _, call)] = dialect.calls
    assert operation == "insert_ignore"
    assert call["table"] is Course.__table__
    assert call["conflict_columns"] == IDENTITY_COLUMNS
