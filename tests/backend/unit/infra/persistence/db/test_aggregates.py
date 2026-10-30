"""Child-collection writes for aggregate roots, verified on the statements they issue."""
import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete, Insert, Update

from backend.domain.entities.wlu.loris_registration import CourseMeetingTime, CourseTermUpdate
from backend.infra.persistence.db.school.school_tables import (
    Course,
    CourseTerm,
    CourseTermFaculty,
    CourseTermMeeting,
)
from backend.infra.persistence.db.utils.generic.aggregates import (
    child_collections,
    replace_children,
    split_children,
    update_aggregate,
    upsert_aggregate,
)


class Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def all(self):
        return self._rows


class RecordingSession:
    """Records (statement, parameters); SELECTs are answered from a queue."""

    def __init__(self, *select_results):
        self.calls = []
        self._selects = list(select_results)

    async def execute(self, stmt, params=None, **_):
        self.calls.append((stmt, params))
        is_write = isinstance(stmt, (Delete, Insert, Update))
        return Result() if is_write else Result(self._selects.pop(0))

    def of(self, kind):
        return [(stmt, params) for stmt, params in self.calls if isinstance(stmt, kind)]


class RecordingDialect:
    def __init__(self, ids):
        self.ids, self.rows = ids, None

    async def upsert(self, session, *, rows, **_):
        self.rows = rows
        return self.ids


MEETING = {"beginTime": "1000", "room": "LH1009", "monday": True}
FACULTY = {"bannerId": "100", "displayName": "Heider Ali"}


def test_collections_are_the_owned_one_to_many_relationships():
    assert set(child_collections(CourseTerm)) == {"meetings", "faculty"}
    assert set(child_collections(Course)) == {"terms"}  # Never in a Course payload, so never split.


def test_split_moves_collections_out_of_the_column_values():
    parents, children = split_children(CourseTerm, [{"crn": "1", "meetings": [MEETING], "faculty": None}])

    assert parents == [{"crn": "1"}]
    # A None collection means "leave unchanged", so it is not replaced.
    assert children == [{"meetings": [MEETING]}]


async def test_replace_deletes_current_rows_then_inserts_items_in_order():
    session = RecordingSession()

    await replace_children(session, CourseTerm, [10, 11], [{"meetings": [MEETING, MEETING]}, {"meetings": []}])

    [(delete_stmt, _)] = session.of(Delete)
    sql = str(delete_stmt.compile(dialect=postgresql.dialect()))
    assert sql.startswith("DELETE FROM course_term_meetings WHERE course_term_meetings.course_term_id IN")
    assert delete_stmt.compile().params == {"course_term_id_1": [10, 11]}

    [(insert_stmt, rows)] = session.of(Insert)
    assert insert_stmt.table.name == CourseTermMeeting.__tablename__
    # An empty list clears the collection: parent 11 is deleted from but gets no rows.
    assert [(row["course_term_id"], row["position"], row["room"]) for row in rows] == [
        (10, 0, "LH1009"), (10, 1, "LH1009"),
    ]
    assert rows[0]["friday"] is None  # Unset fields are written as NULL, not skipped.


async def test_only_collections_present_in_the_payload_are_touched():
    session = RecordingSession()

    await replace_children(session, CourseTerm, [10], [{"faculty": [FACULTY]}])

    assert [stmt.table.name for stmt, _ in session.calls] == ["course_term_faculty", "course_term_faculty"]


async def test_unknown_item_fields_are_rejected_not_dropped():
    with pytest.raises(ValueError, match="CourseTermMeeting has no columns for \\['days'\\]"):
        await replace_children(RecordingSession(), CourseTerm, [10], [{"meetings": [{"days": {}}]}])


async def test_upsert_writes_parents_through_the_dialect_then_replaces_children_by_identity():
    rows = [
        {"term_code": "202609", "crn": "1", "meetings": [MEETING]},
        {"term_code": "202609", "crn": "2", "meetings": []},
    ]
    # Identity lookup answers out of input order; ids must still pair with the right section.
    session = RecordingSession([(21, "202609", "2"), (20, "202609", "1")])
    dialect = RecordingDialect(ids=[21, 20])

    ids = await upsert_aggregate(
        session, dialect, model=CourseTerm, rows=rows, conflict_columns=["term_code", "crn"],
        build_updates=lambda existing, incoming: {},
    )

    assert ids == [21, 20]
    assert dialect.rows == [{"term_code": "202609", "crn": "1"}, {"term_code": "202609", "crn": "2"}]
    [(_, inserted)] = session.of(Insert)
    assert [row["course_term_id"] for row in inserted] == [20]


async def test_upsert_without_collections_skips_the_identity_lookup():
    session = RecordingSession()

    await upsert_aggregate(
        session, RecordingDialect(ids=[1]), model=CourseTerm, rows=[{"term_code": "202609", "crn": "1"}],
        conflict_columns=["term_code", "crn"], build_updates=lambda existing, incoming: {},
    )

    assert session.calls == []


async def test_update_patches_set_columns_and_replaces_set_collections():
    session = RecordingSession()

    await update_aggregate(
        session, CourseTerm, [5, 6], CourseTermUpdate(needs_embedding=False, meetings=[CourseMeetingTime(room="A1")]),
        aliases={},
    )

    [(update_stmt, _)] = session.of(Update)
    assert update_stmt.compile().params["needs_embedding"] is False
    [(_, inserted)] = session.of(Insert)
    assert [(row["course_term_id"], row["room"]) for row in inserted] == [(5, "A1"), (6, "A1")]


async def test_update_leaves_unset_collections_alone():
    session = RecordingSession()

    await update_aggregate(session, CourseTerm, [5], CourseTermUpdate(needs_embedding=False), aliases={})

    assert [type(stmt) for stmt, _ in session.calls] == [Update]


def test_faculty_attributes_are_domain_names_over_snake_case_columns():
    columns = {attr: getattr(CourseTermFaculty, attr).property.columns[0].name for attr in FACULTY}
    assert columns == {"bannerId": "banner_id", "displayName": "display_name"}
