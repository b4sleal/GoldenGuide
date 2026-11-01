"""Entry point of query routing: deterministic entity extraction, then an LLM-planned, validated retrieval plan."""
import structlog

from backend.application.services.router.conversation_entities import relabel_earlier
from backend.application.services.router.extraction.entity_extractor import (
    PreLLMExtractor,
)
from backend.application.services.router.planning.llm.llm_planner import LLMQueryPlanner
from backend.domain.entities.question import EntityMap
from backend.domain.entities.retrieval_plan import PreLLMExtraction
from goldenguide_common.logging.trace_wrapper import traced

logger = structlog.get_logger(__name__)


class QueryRouter:
    """The router: extract entities deterministically, then plan retrieval with the LLM.

        question -> PreLLMExtractor -> MaskedQuestion -> LLMQueryPlanner -> plan
    """

    def __init__(self, extractor: PreLLMExtractor, llm_planner: LLMQueryPlanner):
        self.extractor = extractor
        self.llm_planner = llm_planner

    @traced("router.route")
    async def route(self, question: str, earlier: EntityMap) -> tuple[PreLLMExtraction, EntityMap, EntityMap]:
        """(validated retrieval plan, this question's entities, earlier entities under EARLIER_ masks).

        `earlier` is what the previous turn carried forward; the plan's masks refer to either map.
        """
        masked = await self.extractor.extract_and_mask(question)
        # The masked text can still hold unrecognized personal names, so it is debug-only.
        logger.debug("router_masked_question", masked_question=masked.text)

        carried = relabel_earlier(earlier, masked.entities)
        return await self.llm_planner.plan(question, masked, carried), masked.entities, carried
