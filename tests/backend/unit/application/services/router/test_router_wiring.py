"""RouterContainer resolves the production router graph: catches wiring mistakes before startup does."""
from unittest.mock import Mock

from backend.application.services.router.extraction.matchers.course_matcher import (
    CourseCodeMatcher,
)
from backend.application.services.router.extraction.matchers.department_hint_matcher import (
    DepartmentHintMatcher,
)
from backend.application.services.router.extraction.matchers.instructor_matcher import (
    InstructorMatcher,
)
from backend.application.services.router.extraction.matchers.lexicon_matcher import (
    LexiconEntityMatcher,
)
from backend.application.services.router.extraction.matchers.room_matcher import (
    RoomMatcher,
)
from backend.application.services.router.planning.llm.llm_planner import LLMQueryPlanner
from backend.application.services.router.router import (
    QueryRouter,
)
from backend.core.di.wiring.router import RouterContainer
from tests.backend.unit.application.services.router.factories import (
    INSTITUTION,
    ROUTER_SETTINGS,
)


def container(lexicon_resolver):
    router = RouterContainer(
        school_db=Mock(), cache=Mock(), llm=Mock(), settings=Mock(),
        retrieval_profiles=Mock(), lexicon_resolver=lexicon_resolver,
        institution=INSTITUTION, router_settings=ROUTER_SETTINGS,
    )
    return router


def test_query_router_plans_with_the_llm(lexicon_resolver):
    query_router = container(lexicon_resolver).query_router()

    assert isinstance(query_router, QueryRouter)
    assert isinstance(query_router.llm_planner, LLMQueryPlanner)


def test_matcher_order(lexicon_resolver):
    extractor = container(lexicon_resolver).pre_llm_extractor()

    # Courses before rooms (a valid course code is never re-read as a room); instructors before the
    # lexicon (a name is never split into discipline words).
    assert [type(matcher) for matcher in extractor.matchers] == [
        CourseCodeMatcher, RoomMatcher, InstructorMatcher, LexiconEntityMatcher, DepartmentHintMatcher,
    ]
