import pytest

from backend.application.services.router.compilation.course_compiler import (
    CourseQueryCompiler,
)
from backend.domain.entities.retrieval_plan import (
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)
from tests.backend.unit.application.services.router.factories import (
    CS,
    INSTITUTION,
    LH1009,
    subject,
)

ENTITIES = {
    "[DEPARTMENT1]": CS,
    "[SUBJECT1]": subject("Computer Science", "CP"),
    "[ROOM1]": LH1009,
}


def compile_filter(masks, filters=None):
    return CourseQueryCompiler(INSTITUTION).compile(
        RetrievalRequest(
            source=RetrievalSource.COURSES,
            operation=RetrievalOperation.FILTER,
            entities=masks,
            filters=filters,
        ),
        PreLLMExtraction(),
        ENTITIES,
    )


def test_filter_reads_subjects_from_entities():
    # Regression: subject masks in `entities` were ignored, producing an unfiltered course query.
    [result] = compile_filter(["[DEPARTMENT1]"])
    assert result.subject_code == "CP"


def test_same_code_from_both_places_compiles_once():
    result = compile_filter(["[SUBJECT1]"], GlobalFilters(subjects=["[DEPARTMENT1]"]))
    assert [f.subject_code for f in result] == ["CP"]


def test_rooms_are_not_a_course_filter():
    with pytest.raises(NotImplementedError):
        compile_filter(["[SUBJECT1]"], GlobalFilters(rooms=["LH1009"]))


def test_instructors_are_not_a_course_filter():
    with pytest.raises(NotImplementedError):
        compile_filter(["[SUBJECT1]"], GlobalFilters(instructors=["[INSTRUCTOR1]"]))


def test_non_subject_request_entity_is_rejected():
    # A room in a course listing would otherwise be dropped silently, widening the query.
    with pytest.raises(ValueError, match="Invalid subject entity"):
        compile_filter(["[ROOM1]"])


def test_unsupported_filter_names_the_field():
    with pytest.raises(NotImplementedError, match="term"):
        compile_filter(["[SUBJECT1]"], GlobalFilters(term=["winter"]))


def test_wrong_source_is_an_error_not_an_empty_result():
    # Regression: a non-course request compiled to [], which read downstream as "no courses found".
    with pytest.raises(ValueError, match="Expected courses source"):
        CourseQueryCompiler(INSTITUTION).compile(
            RetrievalRequest(source=RetrievalSource.COURSE_TERMS, operation=RetrievalOperation.LOOKUP),
            PreLLMExtraction(),
            ENTITIES,
        )
