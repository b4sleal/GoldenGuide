from backend.application.services.router.router import QueryRouter
from backend.domain.entities.question import MaskedQuestion
from backend.domain.entities.retrieval_plan import PreLLMExtraction
from tests.backend.unit.application.services.router.factories import LH1009

LLM_PLAN = PreLLMExtraction()
MASKED = MaskedQuestion(text="anything in [ROOM1]", entities={"[ROOM1]": LH1009})


class FakeExtractor:
    def __init__(self):
        self.calls = 0

    async def extract_and_mask(self, question):
        self.calls += 1
        return MASKED


class FakeLLMPlanner:
    def __init__(self):
        self.calls = []

    async def plan(self, question, masked):
        self.calls.append((question, masked))
        return LLM_PLAN


async def test_question_is_planned_by_the_llm_with_the_extraction():
    extractor, llm = FakeExtractor(), FakeLLMPlanner()

    plan, entities = await QueryRouter(extractor, llm).route("anything in LH1009")

    assert plan is LLM_PLAN
    assert llm.calls == [("anything in LH1009", MASKED)]   # Original question plus the one extraction.
    assert extractor.calls == 1                             # Entities are extracted once per question.
    assert entities == MASKED.entities
