"""Carried entities: relabelled so they never collide, deduplicated, and dropped when unused."""
from backend.application.services.router.conversation_entities import (
    entities_to_carry,
    relabel_earlier,
)
from backend.domain.entities.question import CourseEntity, DisciplineEntity, EntityType

CP264 = CourseEntity(raw="cp264", normalized="CP264")
CP164 = CourseEntity(raw="CP164", normalized="CP164")
COMPUTING = DisciplineEntity(type=EntityType.SUBJECT, canonical="Computer Science", code="CP")


def test_earlier_entities_get_their_own_masks_numbered_by_type():
    relabelled = relabel_earlier({"[COURSE1]": CP264, "[COURSE2]": CP164, "[SUBJECT1]": COMPUTING}, current={})

    assert relabelled == {"[EARLIER_COURSE1]": CP264, "[EARLIER_COURSE2]": CP164, "[EARLIER_SUBJECT1]": COMPUTING}


def test_an_entity_named_again_now_is_not_carried_twice():
    # Written differently this time ("CP264" vs "cp264"): still the same course.
    current = {"[COURSE1]": CourseEntity(raw="CP264", normalized="CP264")}

    assert relabel_earlier({"[COURSE1]": CP264, "[COURSE2]": CP164}, current) == {"[EARLIER_COURSE1]": CP164}


def test_carry_this_questions_entities_and_only_the_earlier_ones_it_used():
    carried = entities_to_carry(
        current={"[SUBJECT1]": COMPUTING},
        earlier={"[EARLIER_COURSE1]": CP264, "[EARLIER_COURSE2]": CP164},
        referenced={"[EARLIER_COURSE1]", "[SUBJECT1]"},
    )

    assert carried == {"[SUBJECT1]": COMPUTING, "[EARLIER_COURSE1]": CP264}


def test_a_change_of_topic_ends_the_old_context():
    assert entities_to_carry(current={}, earlier={"[EARLIER_COURSE1]": CP264}, referenced=set()) == {}
