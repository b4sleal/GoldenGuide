"""Course-term reads: collections load on demand and filters compile to portable SQL."""
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import mysql, postgresql

from backend.domain.entities.wlu.loris_registration import (
    CourseFaculty,
    CourseMeetingTime,
    CourseTermRead,
    MeetingRoom,
)
from backend.domain.ports.repositories.filters import CourseTermFilter
from backend.infra.persistence.db.school.filters import CourseTermFilterTranslator
from backend.infra.persistence.db.school.school_tables import CourseTerm, CourseTermFaculty, CourseTermMeeting
from backend.infra.persistence.db.utils.sql_view import apply_view
from pydantic import BaseModel


class TitleOnly(BaseModel):
    title: str | None


class WithMeetings(BaseModel):
    title: str | None
    meetings: list[CourseMeetingTime]


def loaded_relationships(stmt) -> set[str]:
    """Relationships the statement eager-loads with selectin."""
    return {
        load.path[1].key
        for option in stmt._with_options
        for load in option.context
        if dict(load.strategy or ()).get("lazy") == "selectin"
    }


def test_views_without_collections_do_not_load_them():
    assert loaded_relationships(apply_view(select(CourseTerm), TitleOnly, CourseTerm)) == set()


def test_views_with_collections_eager_load_only_those():
    assert loaded_relationships(apply_view(select(CourseTerm), WithMeetings, CourseTerm)) == {"meetings"}


def test_loaded_child_rows_validate_into_the_domain_read_model():
    row = {
        "id": 1, "course_id": 1, "term_code": "202609", "crn": "1001", "subject": "Computer Science", "subject_code": "CP", "course_number": "220",
        "meetings": [CourseTermMeeting(room="LH1009", monday=True, beginTime="1000", position=0)],
        "faculty": [CourseTermFaculty(bannerId="100", displayName="Heider Ali", position=0)],
    }

    read = CourseTermRead.model_validate(row, from_attributes=True)

    assert read.meetings == [CourseMeetingTime(room="LH1009", monday=True, beginTime="1000")]
    assert read.faculty == [CourseFaculty(bannerId="100", displayName="Heider Ali")]


def compile_filter(filters: CourseTermFilter, dialect) -> str:
    stmt = CourseTermFilterTranslator.apply(select(CourseTerm.id), filters)
    return str(stmt.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("dialect", [postgresql.dialect(), mysql.dialect()], ids=["postgresql", "mysql"])
def test_collection_and_column_filters_compile_on_every_dialect(dialect):
    sql = compile_filter(
        CourseTermFilter(
            instructor_ids=["100"], rooms=[MeetingRoom(building="LH", room="LH1009")],
            day_preference=["friday"], day_exclusion=["monday"], has_seats=True, credit=[0.5],
        ),
        dialect,
    )

    assert "jsonb" not in sql.lower()
    assert "EXISTS (SELECT 1 \nFROM course_term_faculty" in sql
    assert "course_term_faculty.banner_id IN ('100')" in sql
    assert "course_terms.seats_available > 0" in sql
    assert "course_terms.credit_hours IN (0.5)" in sql


def test_room_and_day_are_required_on_the_same_meeting():
    sql = compile_filter(
        CourseTermFilter(rooms=[MeetingRoom(building="LH", room="LH1009")], day_preference=["friday"]),
        postgresql.dialect(),
    )

    # One EXISTS holds both conditions; a second, bare EXISTS requires any meeting at all.
    assert sql.count("EXISTS (SELECT 1 \nFROM course_term_meetings") == 2
    assert ("course_term_meetings.room = 'LH1009' AND course_term_meetings.building = 'LH' "
            "AND course_term_meetings.friday IS true") in sql


def test_room_without_a_building_matches_a_null_building():
    sql = compile_filter(CourseTermFilter(rooms=[MeetingRoom(building=None, room="P118")]), postgresql.dialect())

    assert "course_term_meetings.building IS NULL" in sql


def test_day_exclusion_rejects_any_meeting_on_that_day():
    sql = compile_filter(CourseTermFilter(day_exclusion=["monday"]), postgresql.dialect())

    assert "NOT (EXISTS (SELECT 1 \nFROM course_term_meetings" in sql
    assert "course_term_meetings.monday IS true" in sql


def test_unknown_day_names_fail_loudly():
    with pytest.raises(ValueError):
        compile_filter(CourseTermFilter(day_preference=["funday"]), postgresql.dialect())
