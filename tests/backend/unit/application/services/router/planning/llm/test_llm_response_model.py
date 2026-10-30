"""LLM output parsing: lenient shapes are repaired at the boundary; domain models stay strict."""
import pytest
from pydantic import ValidationError

from backend.application.services.router.planning.llm.response_model import (
    LLMPlanResponse,
)
from backend.domain.entities.retrieval_plan import GlobalFilters, PreLLMExtraction
from backend.domain.entities.wlu.academic_calendar import Season


def parse(**fields) -> LLMPlanResponse:
    return LLMPlanResponse.model_validate(fields)


def filters_of(**filters) -> GlobalFilters:
    return parse(global_filters=filters).global_filters


def test_single_value_where_a_list_is_expected():
    assert filters_of(term="winter").term == [Season.WINTER]
    assert filters_of(level=100).level == [100]


def test_lists_pass_through():
    assert filters_of(term=["winter", "fall"]).term == [Season.WINTER, Season.FALL]


def test_nothing_is_invented():
    result = filters_of()
    assert result.term is None and result.year is None and result.day_preference is None


def test_invalid_values_still_fail():
    with pytest.raises(ValidationError):
        filters_of(term="banana")


def test_boolean_is_not_coerced_to_list():
    with pytest.raises(ValidationError):
        filters_of(year=True)


def test_single_request_object_becomes_a_list():
    result = parse(retrieval={
        "requests": {"source": "courses", "operation": "lookup", "entities": "[COURSE1]"},
        "semantic_fallback": False,
    })
    [request] = result.retrieval.requests
    assert request.entities == ["[COURSE1]"]


def test_nested_request_filters_are_repaired():
    result = parse(retrieval={"requests": [{
        "source": "course_terms", "operation": "filter", "entities": ["[SUBJECT1]"],
        "filters": {"term": "winter", "day_preference": "friday"},
    }]})
    filters = result.retrieval.requests[0].filters
    assert (filters.term, filters.day_preference) == (["winter"], ["friday"])


def test_course_specific_single_target_term():
    result = parse(course_specific_filters={"[COURSE1]": {"target_terms": {"term": "winter"}}})
    assert result.course_specific_filters["[COURSE1]"].target_terms[0].term == Season.WINTER


def test_null_objects_use_their_defaults():
    # Regression: "global_filters": null used to discard the whole plan.
    result = parse(
        global_filters=None,
        conversation_context=None,
        retrieval={"requests": [{"source": "course_terms", "operation": "lookup", "entities": ["[COURSE1]"]}],
                   "semantic_fallback": False},
    )
    assert result.global_filters == GlobalFilters()
    assert result.retrieval.requests[0].source.value == "course_terms"


def test_null_optional_fields_stay_null():
    assert parse(retrieval={"requests": [{"source": "vector", "operation": "semantic", "filters": None}]}) \
        .retrieval.requests[0].filters is None


def test_response_is_a_plan_with_the_same_schema():
    result = parse()
    assert isinstance(result, PreLLMExtraction)
    assert LLMPlanResponse.model_json_schema()["properties"] == PreLLMExtraction.model_json_schema()["properties"]


def test_domain_models_stay_strict():
    # The leniency exists only for LLM output: domain models reject the same shapes.
    with pytest.raises(ValidationError):
        GlobalFilters.model_validate({"term": "winter"})
