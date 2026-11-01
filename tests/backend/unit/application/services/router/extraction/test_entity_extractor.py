"""PreLLMExtractor with the production matcher chain and the real lexicon (fixtures in conftest.py)."""
from backend.application.services.router.extraction.entity_extractor import (
    PreLLMExtractor,
)
from backend.application.services.router.extraction.matchers.base import MaskingState
from backend.domain.entities.question import (
    CourseEntity,
    DisciplineEntity,
    EntityLookup,
    EntityType,
    MaskedQuestion,
    RoomEntity,
)
from backend.domain.entities.wlu.loris_registration import MeetingRoom


async def test_course_codes_are_masked(extractor):
    masked = await extractor.extract_and_mask("Do I need CP213 before cp 317?")

    # Mask numbers follow matcher passes (subject-alias form first), not sentence position.
    by_code = {entity.normalized: mask for mask, entity in masked.entities.items()}
    assert masked.text == f"Do I need {by_code['CP213']} before {by_code['CP317']}?"
    assert set(by_code.values()) == {"[COURSE1]", "[COURSE2]"}
    assert masked.entities[by_code["CP213"]] == CourseEntity(raw="CP213", normalized="CP213")


async def test_subject_alias_course_is_masked(extractor):
    masked = await extractor.extract_and_mask("is comp sci 104 hard")

    assert masked.text == "is [COURSE1] hard"
    assert masked.entities["[COURSE1]"].normalized == "CP104"


async def test_unknown_course_code_is_left_alone(extractor):
    assert await extractor.extract_and_mask("what is CP999") == MaskedQuestion(text="what is CP999")


async def test_subject_name_resolves_to_its_code(extractor):
    masked = await extractor.extract_and_mask("Courses in computer science")

    [(mask, entity)] = masked.entities.items()
    assert masked.text == f"Courses in {mask}"
    assert isinstance(entity, DisciplineEntity)
    assert entity.type in {EntityType.SUBJECT, EntityType.DEPARTMENT}
    assert (entity.canonical, entity.code) == ("Computer Science", "CP")


async def test_room_and_day_question(extractor):
    masked = await extractor.extract_and_mask("is there any courses in LH1009 on fridays")

    assert masked == MaskedQuestion(
        text="is there any courses in [ROOM1] on fridays",
        entities={"[ROOM1]": RoomEntity(
            raw="LH1009", canonical="LH1009", rooms=[MeetingRoom(building="LH", room="LH1009")],
        )},
    )


async def test_course_matcher_runs_before_room_matcher(extractor):
    # BA101 is both a catalog course and a room; the course matcher claims it first (DI order).
    masked = await extractor.extract_and_mask("what is BA101 about")
    assert masked.text == "what is [COURSE1] about"
    assert isinstance(masked.entities["[COURSE1]"], CourseEntity)


async def test_matchers_run_in_order_and_see_earlier_masks():
    seen = []

    class Recorder:
        def __init__(self, name):
            self.name = name

        def apply(self, state: MaskingState, lookup: EntityLookup):
            seen.append((self.name, state.text))
            state.text = state.text.replace(self.name, f"[{self.name.upper()}1]")

    class Cache:
        async def get_lookup_data(self):
            return EntityLookup()

    masked = await PreLLMExtractor(Cache(), [Recorder("a"), Recorder("b")]).extract_and_mask("a b")

    assert seen == [("a", "a b"), ("b", "[A1] b")]
    assert masked.text == "[A1] [B1]"


def test_masks_are_numbered_per_entity_type():
    state = MaskingState(text="")
    assert [state.next_mask(EntityType.COURSE), state.next_mask(EntityType.ROOM), state.next_mask(EntityType.COURSE)] == [
        "[COURSE1]", "[ROOM1]", "[COURSE2]",
    ]


async def test_a_pronoun_that_spells_a_subject_code_is_not_an_entity(extractor):
    # Regression: Italian's code is IT, so "is it offered" became "is [DEPARTMENT1] offered" and a
    # follow-up question searched Italian instead of the course it referred to.
    masked = await extractor.extract_and_mask("Is it offered in winter?")

    assert masked.entities == {}
    assert masked.text == "Is it offered in winter?"


async def test_a_subject_code_written_in_capitals_still_matches(extractor):
    masked = await extractor.extract_and_mask("Which IT courses run in winter?")

    [entity] = masked.entities.values()
    assert isinstance(entity, DisciplineEntity) and entity.canonical == "Italian"


async def test_subject_names_still_match_in_any_case(extractor):
    masked = await extractor.extract_and_mask("which italian courses run in winter?")

    [entity] = masked.entities.values()
    assert isinstance(entity, DisciplineEntity) and entity.canonical == "Italian"
