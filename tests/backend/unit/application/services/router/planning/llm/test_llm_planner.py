from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.application.services.router.planning.llm.llm_planner import LLMQueryPlanner
from backend.domain.entities.question import MaskedQuestion
from backend.domain.entities.retrieval_plan import (
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from tests.backend.unit.application.services.router.factories import course

PROMPT = "today={current_date} term={active_term} q={question} e={entities}"
ENTITIES = {"[COURSE1]": course("CP220")}


def planner(llm_result=None, llm_error=None) -> tuple[LLMQueryPlanner, AsyncMock]:
    llm = Mock()
    llm.generate_structured = AsyncMock(return_value=llm_result, side_effect=llm_error)
    settings = Mock()
    settings.get = AsyncMock(return_value=SimpleNamespace(router_llm=SimpleNamespace(system="ROUTER RULES", turn=PROMPT)))
    profiles = Mock()
    profiles.route_question.return_value = SimpleNamespace(llm=Mock())
    clock = AcademicTermResolver(clock=lambda: date(2027, 2, 10))
    return LLMQueryPlanner(llm, settings, profiles, clock), llm.generate_structured


def lookup(*masks) -> PreLLMExtraction:
    return PreLLMExtraction(retrieval=RetrievalPlan(requests=[
        RetrievalRequest(source=RetrievalSource.COURSES, operation=RetrievalOperation.LOOKUP, entities=list(masks)),
    ]))


async def plan(planner_):
    return await planner_.plan("is cp220 hard", MaskedQuestion(text="is [COURSE1] hard", entities=ENTITIES), {})


async def test_prompt_date_and_term_come_from_the_injected_clock():
    # Regression: the prompt date read the wall clock while the term read the resolver.
    planner_, generate = planner(lookup("[COURSE1]"))
    await plan(planner_)
    request = generate.await_args.args[0]
    [message] = request.messages
    assert "today=2027-02-10 term=202701" in message.content
    assert request.system == "ROUTER RULES"   # Fixed instructions stay out of the per-question turn.


async def test_valid_plan_is_kept():
    planner_, _ = planner(lookup("[COURSE1]"))
    assert await plan(planner_) == lookup("[COURSE1]")


async def test_rejected_plan_falls_back():
    # The LLM invented an entity: the conservative fallback looks up the course actually mentioned.
    planner_, _ = planner(lookup("[COURSE9]"))
    result = await plan(planner_)
    [request] = result.retrieval.requests
    assert request.entities == ["[COURSE1]"] and request.operation == RetrievalOperation.LOOKUP


async def test_outages_and_bugs_are_not_mistaken_for_a_bad_plan():
    planner_, _ = planner(llm_error=RuntimeError("All structured LLM targets failed"))
    with pytest.raises(RuntimeError):
        await plan(planner_)


async def test_a_follow_up_may_use_an_entity_carried_from_earlier():
    # "is it offered in winter?": no course of its own, CP264 carried from the previous answer.
    planner_, generate = planner(lookup("[EARLIER_COURSE1]"))
    earlier = {"[EARLIER_COURSE1]": course("CP264")}

    result = await planner_.plan("is it offered in winter?", MaskedQuestion(text="is it offered in winter?"), earlier)

    assert result == lookup("[EARLIER_COURSE1]")
    [message] = generate.await_args.args[0].messages
    assert "[EARLIER_COURSE1]" in message.content   # The router is shown the carried entity.


async def test_a_course_code_written_instead_of_its_mask_is_resolved_not_rejected():
    # The router LLM sometimes copies the code it saw ("CP164") instead of the mask.
    planner_, _ = planner(lookup("CP164"))
    earlier = {"[EARLIER_COURSE1]": course("CP164")}

    result = await planner_.plan("what are its prerequisites?", MaskedQuestion(text="what are its prerequisites?"), earlier)

    assert result == lookup("[EARLIER_COURSE1]")


async def test_a_course_code_no_entity_has_is_still_rejected():
    planner_, _ = planner(lookup("CP999"))

    result = await plan(planner_)

    assert result.retrieval.requests[0].entities == ["[COURSE1]"]   # Conservative fallback, not CP999.
