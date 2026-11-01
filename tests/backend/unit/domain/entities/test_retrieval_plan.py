"""The retrieval plan is pure, strict data: enums validate values, nothing is coerced."""
import pytest
from pydantic import ValidationError

from backend.domain.entities.retrieval_plan import (
    GlobalFilters,
)
from backend.domain.entities.wlu.academic_calendar import Season, Weekday


def test_terms_and_days_are_enums():
    filters = GlobalFilters(term=["winter"], day_preference=["friday"])
    assert filters.term == [Season.WINTER]
    assert filters.day_preference == [Weekday.FRIDAY]


@pytest.mark.parametrize("fields", [{"term": ["banana"]}, {"day_preference": ["funday"]}, {"term": "winter"}])
def test_invalid_or_unshaped_values_are_rejected(fields):
    with pytest.raises(ValidationError):
        GlobalFilters.model_validate(fields)


def test_no_invented_defaults():
    filters = GlobalFilters()
    assert filters.term is None and filters.year is None and filters.day_preference is None
