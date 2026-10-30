"""Date scope for dates-and-deadlines answers: the current term, plus the next one past its midpoint."""
from datetime import date

import pytest

from backend.application.use_cases.chatbot.date_scope import terms_to_cover
from backend.domain.entities.wlu.academic_term import AcademicTermResolver


def resolver(day: date) -> AcademicTermResolver:
    return AcademicTermResolver(clock=lambda: day)


@pytest.mark.parametrize(("day", "past"), [
    (date(2026, 9, 1), False),    # Fall: Sep-Dec, midpoint at November.
    (date(2026, 10, 31), False),
    (date(2026, 11, 1), True),
    (date(2026, 12, 15), True),
    (date(2027, 2, 28), False),   # Winter: Jan-Apr, midpoint at March.
    (date(2027, 3, 1), True),
    (date(2027, 6, 30), False),   # Spring/Summer: May-Aug, midpoint at July.
    (date(2027, 7, 1), True),
])
def test_past_midpoint(day, past):
    assert resolver(day).past_midpoint() is past


def test_first_half_covers_the_whole_current_term():
    assert terms_to_cover(resolver(date(2026, 10, 27))) == "Fall 2026 (the whole term)"


def test_second_half_covers_the_rest_of_this_term_then_the_next():
    scope = terms_to_cover(resolver(date(2026, 12, 2)))

    assert scope.startswith("Fall 2026 (dates from today on;")
    assert scope.endswith("then Winter 2027")


def test_winter_rolls_into_spring():
    assert terms_to_cover(resolver(date(2027, 3, 15))).endswith("then Spring 2027")
