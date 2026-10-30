from datetime import date

import pytest

from backend.application.services.router.compilation.course_term_compiler import (
    CourseTermQueryCompiler,
)
from backend.domain.entities.retrieval_plan import (
    CourseSpecificFilters,
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
    TermYearCombo,
)
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.entities.wlu.loris_registration import MeetingRoom
from tests.backend.unit.application.services.router.factories import (
    CS,
    HEIDER_ALI,
    LH1009,
    course,
    department,
    room,
    subject,
)


@pytest.fixture
def compiler():
    # Real term rules, with "today" pinned to October 2026 (Fall 2026 in progress).
    return CourseTermQueryCompiler(AcademicTermResolver(clock=lambda: date(2026, 10, 20)))


@pytest.fixture
def entities():
    return {
        "[COURSE1]": course("CP213"),
        "[SUBJECT1]": subject("Computer Science", "CP"),
        "[ROOM1]": LH1009,
        "[INSTRUCTOR1]": HEIDER_ALI,
        "[ROOM2]": room(("AA", "101X"), ("BB", "101X")),
    }


def request(*, masks, filters=None):
    return RetrievalRequest(
        source=RetrievalSource.COURSE_TERMS,
        operation=RetrievalOperation.FILTER,
        entities=masks,
        filters=filters,
    )


def test_exact_course_uses_active_term(compiler, entities):
    result = compiler.compile(
        request(masks=["[COURSE1]"]),
        PreLLMExtraction(),
        entities,
    )

    assert len(result) == 1
    assert result[0].term_code == "202609"
    assert result[0].subject_code == "CP"
    assert result[0].course_number == "213"


def test_subject_level_and_days(compiler, entities):
    result = compiler.compile(
        request(
            masks=["[SUBJECT1]"],
            filters=GlobalFilters(
                level=[200],
                day_exclusion=["friday"],
            ),
        ),
        PreLLMExtraction(),
        entities,
    )

    assert len(result) == 1
    assert result[0].levels == [200]
    assert result[0].day_exclusion == ["friday"]


def test_unsupported_filter_fails(compiler, entities):
    with pytest.raises(NotImplementedError):
        compiler.compile(
            request(
                masks=["[COURSE1]"],
                filters=GlobalFilters(delivery=["online"]),
            ),
            PreLLMExtraction(),
            entities,
        )


def test_requests_do_not_share_filters(compiler, entities):
    winter = request(
        masks=["[COURSE1]"],
        filters=GlobalFilters(term=["winter"], year=[2027]),
    )
    current = request(masks=["[COURSE1]"])

    first = compiler.compile(winter, PreLLMExtraction(), entities)
    second = compiler.compile(current, PreLLMExtraction(), entities)

    assert first[0].term_code == "202701"
    assert second[0].term_code == "202609"

def test_bare_season_means_its_next_occurrence(compiler, entities):
    # Regression: "cp220 in winter?" asked in October used to fail with
    # "Term and year must be provided together" and silently lose the term filter.
    result = compiler.compile(
        request(masks=["[COURSE1]"], filters=GlobalFilters(term=["winter"])),
        PreLLMExtraction(),
        entities,
    )
    assert [f.term_code for f in result] == ["202701"]


def test_year_only_covers_every_term_that_year(compiler, entities):
    result = compiler.compile(
        request(masks=["[COURSE1]"], filters=GlobalFilters(year=[2027])),
        PreLLMExtraction(),
        entities,
    )
    assert [f.term_code for f in result] == ["202701", "202705", "202709"]


def test_department_counts_as_subject(compiler, entities):
    # Regression: the lexicon tags "computer science" as a department; it used to be dropped.
    entities = {**entities, "[DEPARTMENT1]": CS}
    for req in (request(masks=["[DEPARTMENT1]"]), request(masks=[], filters=GlobalFilters(subjects=["[DEPARTMENT1]"]))):
        [result] = compiler.compile(req, PreLLMExtraction(), entities)
        assert result.subject_code == "CP"


def test_department_without_code_fails(compiler, entities):
    entities = {**entities, "[DEPARTMENT1]": department("Somewhere", None)}
    with pytest.raises(ValueError, match="Unresolved subject"):
        compiler.compile(request(masks=["[DEPARTMENT1]"]), PreLLMExtraction(), entities)


def test_room_alone_is_an_anchor(compiler, entities):
    result = compiler.compile(
        request(masks=[], filters=GlobalFilters(rooms=["[ROOM1]"], day_preference=["friday"])),
        PreLLMExtraction(),
        entities,
    )
    assert len(result) == 1
    assert result[0].term_code == "202609"
    assert result[0].subject_code is None
    assert result[0].rooms == [MeetingRoom(building="LH", room="LH1009")]
    assert result[0].day_preference == ["friday"]


def test_room_as_request_entity(compiler, entities):
    # The LLM router may put the room mask in `entities` rather than `filters.rooms`.
    [result] = compiler.compile(request(masks=["[ROOM1]"]), PreLLMExtraction(), entities)
    assert result.rooms == [MeetingRoom(building="LH", room="LH1009")]


def test_shared_room_name_expands_to_every_room(compiler, entities):
    [result] = compiler.compile(request(masks=[], filters=GlobalFilters(rooms=["[ROOM2]"])), PreLLMExtraction(), entities)
    assert result.rooms == [MeetingRoom(building="AA", room="101X"), MeetingRoom(building="BB", room="101X")]


def test_room_narrows_a_course_and_subject(compiler, entities):
    result = compiler.compile(
        request(masks=["[COURSE1]", "[SUBJECT1]"], filters=GlobalFilters(rooms=["[ROOM1]"], term=["winter"])),
        PreLLMExtraction(),
        entities,
    )
    assert [(f.term_code, f.subject_code, f.course_number, f.rooms) for f in result] == [
        ("202701", "CP", "213", [MeetingRoom(building="LH", room="LH1009")]),
        ("202701", "CP", None, [MeetingRoom(building="LH", room="LH1009")]),
    ]


@pytest.mark.parametrize("mask", ["[UNKNOWN]", "[SUBJECT1]"])
def test_invalid_room_reference_fails(compiler, entities, mask):
    with pytest.raises(ValueError, match="Invalid room"):
        compiler.compile(request(masks=[], filters=GlobalFilters(rooms=[mask])), PreLLMExtraction(), entities)


def test_no_anchor_still_fails(compiler, entities):
    with pytest.raises(ValueError, match="requires a course, subject, room or instructor"):
        compiler.compile(
            request(masks=[], filters=GlobalFilters(day_preference=["friday"])),
            PreLLMExtraction(),
            entities,
        )


def test_course_specific_season_without_year(compiler, entities):
    extraction = PreLLMExtraction(
        course_specific_filters={
            "[COURSE1]": CourseSpecificFilters(target_terms=[TermYearCombo(term="winter")]),
        }
    )
    result = compiler.compile(request(masks=["[COURSE1]"]), extraction, entities)
    assert [f.term_code for f in result] == ["202701"]


def test_instructor_alone_is_an_anchor(compiler, entities):
    [result] = compiler.compile(
        request(masks=[], filters=GlobalFilters(instructors=["[INSTRUCTOR1]"], term=["winter"])),
        PreLLMExtraction(),
        entities,
    )
    assert (result.term_code, result.subject_code, result.instructor_ids) == ("202701", None, ["100"])


def test_instructor_as_request_entity_narrows_a_subject(compiler, entities):
    [result] = compiler.compile(request(masks=["[SUBJECT1]", "[INSTRUCTOR1]"]), PreLLMExtraction(), entities)
    assert (result.subject_code, result.instructor_ids) == ("CP", ["100"])


def test_invalid_instructor_reference_fails(compiler, entities):
    with pytest.raises(ValueError, match="Invalid instructor"):
        compiler.compile(request(masks=[], filters=GlobalFilters(instructors=["[ROOM1]"])), PreLLMExtraction(), entities)
