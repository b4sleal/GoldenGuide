from datetime import date

import pytest

from backend.domain.entities.wlu.academic_term import AcademicTermResolver


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 1, 1), "202601"),
        (date(2026, 4, 30), "202601"),
        (date(2026, 5, 1), "202605"),
        (date(2026, 6, 30), "202605"),
        (date(2026, 7, 1), "202605"),
        (date(2026, 8, 31), "202605"),
        (date(2026, 9, 1), "202609"),
        (date(2026, 12, 31), "202609"),
    ],
)
def test_current_term(day, expected):
    assert AcademicTermResolver(clock=lambda: day).current() == expected


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("winter", "202601"),
        ("spring", "202605"),
        ("intersession", "202605"),
        ("summer", "202605"),
        ("fall", "202609"),
    ],
)
def test_encode(term, expected):
    assert AcademicTermResolver.encode(term, 2026) == expected


def test_invalid_term():
    with pytest.raises(ValueError, match="Unsupported academic term"):
        AcademicTermResolver.encode("autumn", 2026)


OCT_2026 = AcademicTermResolver(clock=lambda: date(2026, 10, 20))   # Fall 2026 in progress
FEB_2027 = AcademicTermResolver(clock=lambda: date(2027, 2, 10))    # Winter 2027 in progress


@pytest.mark.parametrize(
    ("resolver", "terms", "years", "expected"),
    [
        # Bare season: next occurrence, counting the term in progress.
        (OCT_2026, ["winter"], None, ["202701"]),
        (OCT_2026, ["fall"], None, ["202609"]),
        (OCT_2026, ["spring"], None, ["202705"]),
        (FEB_2027, ["winter"], None, ["202701"]),
        (FEB_2027, ["fall"], None, ["202709"]),
        # Season + year: exact.
        (OCT_2026, ["winter"], [2028], ["202801"]),
        (OCT_2026, ["winter", "fall"], [2027], ["202701", "202709"]),
        # Year only: every term in that year.
        (OCT_2026, None, [2027], ["202701", "202705", "202709"]),
        # Nothing: current term.
        (OCT_2026, None, None, ["202609"]),
        # Spring/summer/intersession share one code; no duplicates.
        (OCT_2026, ["spring", "summer"], [2027], ["202705"]),
    ],
)
def test_resolve(resolver, terms, years, expected):
    assert resolver.resolve(terms, years) == expected


def test_upcoming_reads_the_injected_clock():
    # Regression: upcoming()/current() used to read the wall clock, ignoring the injected one.
    assert OCT_2026.upcoming("winter") == "202701"
    assert FEB_2027.upcoming("winter") == "202701"
    assert FEB_2027.upcoming("spring") == "202705"


@pytest.mark.parametrize("today, offset, expected", [
    (date(2026, 10, 23), 0, ("fall", 2026)),
    (date(2026, 10, 23), 1, ("winter", 2027)),
    (date(2026, 10, 23), 2, ("spring", 2027)),
    (date(2026, 10, 23), -1, ("spring", 2026)),
    (date(2027, 2, 1), 1, ("spring", 2027)),
    (date(2027, 6, 1), 1, ("fall", 2027)),
    (date(2027, 6, 1), -2, ("fall", 2026)),
])
def test_shift_steps_through_registration_terms(today, offset, expected):
    assert AcademicTermResolver(clock=lambda: today).shift(offset) == expected
