import pytest

from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.application.services.router.extraction.matchers.instructor_matcher import (
    InstructorMatcher,
    build_instructor_index,
)
from backend.domain.entities.question import EntityLookup, InstructorEntity
from backend.domain.entities.wlu.loris_registration import CourseFaculty

HEIDER = CourseFaculty(bannerId="100", displayName="Heider Ali")


def match(text, lookup):
    state = MaskingState(text=text)
    InstructorMatcher().apply(state, lookup)
    return state


@pytest.mark.parametrize("text", [
    "comp sci courses taught by Heider Ali",
    "comp sci courses taught by heider ali",
    "comp sci courses taught by HEIDER  ALI",
])
def test_full_name_is_masked(lookup, text):
    state = match(text, lookup)

    assert state.text.endswith("taught by [INSTRUCTOR1]")
    assert state.entities["[INSTRUCTOR1]"] == InstructorEntity(
        raw=text[text.index("taught by ") + len("taught by "):],
        canonical="Heider Ali",
        instructors=[HEIDER],
    )


def test_hyphenated_names_match_with_or_without_hyphen(lookup):
    for text in ("courses by Alison Blay-Palmer", "courses by alison blay palmer"):
        assert match(text, lookup).entities["[INSTRUCTOR1]"].instructors == [
            CourseFaculty(bannerId="102", displayName="Alison Blay-Palmer"),
        ]


def test_surname_or_first_name_alone_is_not_an_instructor(lookup):
    # "Ali" is Heider Ali's surname and Ali Hosseini's first name: ambiguous, so never matched.
    assert match("courses by Ali", lookup).entities == {}
    assert match("courses by Heider", lookup).entities == {}


def test_overlapping_names_take_the_longest_at_each_position(lookup):
    # "Heider Ali Hosseini" reads Heider Ali first; "Hosseini" alone is not a full name.
    state = match("Heider Ali Hosseini", lookup)
    assert state.text == "[INSTRUCTOR1] Hosseini"


def test_two_instructors(lookup):
    state = match("Heider Ali or Ali Hosseini", lookup)
    assert state.text == "[INSTRUCTOR1] or [INSTRUCTOR2]"
    assert state.entities["[INSTRUCTOR2]"].canonical == "Ali Hosseini"


def test_index_skips_records_without_identity_or_full_name():
    index = build_instructor_index([
        CourseFaculty(bannerId=None, displayName="No Identity"),
        CourseFaculty(bannerId="1", displayName="Mononym"),
        CourseFaculty(bannerId="2", displayName="Shared Name"),
        CourseFaculty(bannerId="3", displayName="Shared Name"),
    ])
    assert set(index) == {"shared name"}
    assert [instructor.bannerId for instructor in index["shared name"]] == ["2", "3"]


def test_no_instructors_in_lookup_is_a_no_op():
    state = match("Heider Ali", EntityLookup())
    assert (state.text, state.entities) == ("Heider Ali", {})


def test_contact_details_never_reach_the_entity(lookup):
    lookup = lookup.model_copy(update={"instructors": [
        CourseFaculty(bannerId="100", displayName="Heider Ali", emailAddress="hali@wlu.ca", primaryIndicator=True),
    ]})
    assert match("Heider Ali", lookup).entities["[INSTRUCTOR1]"].instructors == [HEIDER]
