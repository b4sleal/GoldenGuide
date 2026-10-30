"""Ask the router LLM for a retrieval plan, validate it against the extracted entities, fall back if rejected."""
import json

import structlog

from backend.application.services.router.planning.llm.plan_validation import (
    PlanRejected,
    fallback_plan,
    normalize_program_operations,
    resolve_subject_references,
    validate_entity_references,
    validate_operations,
)
from backend.application.services.router.planning.llm.response_model import (
    LLMPlanResponse,
)
from backend.domain.entities.question import EntityMap, MaskedQuestion
from backend.domain.entities.retrieval_plan import PreLLMExtraction
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.ports.providers.llm import LLMOrchestrator
from backend.domain.ports.retrieval_profiles import RetrievalProfileSelector
from backend.domain.ports.settings import RuntimeSettingsReader
from goldenguide_common.logging.trace_wrapper import traced

logger = structlog.get_logger(__name__)


def entities_json(entities: EntityMap) -> str:
    """The recognized entities as the router prompt shows them (compact JSON, unset fields omitted)."""
    return json.dumps(
        {mask: entity.model_dump(mode="json", exclude_none=True) for mask, entity in entities.items()},
        separators=(",", ":"),
    )


class LLMQueryPlanner:
    """Plans retrieval with the router LLM, then validates the plan against the extracted entities.

    A plan the validators reject (unknown entity, unsupported operation) is replaced by
    plan_validation.fallback_plan, so a bad plan degrades the answer instead of failing it. Only
    PlanRejected is recovered: any other error is a bug or an outage and propagates.
    """

    def __init__(
            self,
            llm: LLMOrchestrator,
            settings: RuntimeSettingsReader,
            retrieval_router: RetrievalProfileSelector,
            term_resolver: AcademicTermResolver,
    ):
        self.llm = llm
        self.settings = settings
        self.retrieval_router = retrieval_router
        self.term_resolver = term_resolver

    @traced("router.llm_plan")
    async def plan(self, question: str, masked: MaskedQuestion) -> PreLLMExtraction:
        settings = await self.settings.get()
        profile = self.retrieval_router.route_question(question)
        # Date and active term both come from the injected resolver, so they always agree.
        today = self.term_resolver.today()

        prompt = (
            settings.router_llm.prompt
            .replace("{current_date}", today.isoformat())
            .replace("{active_term}", self.term_resolver.current())
            .replace("{question}", f"{question}\nResolved entity references: {masked.text}")
            .replace("{entities}", entities_json(masked.entities))
        )

        try:
            result = await self.llm.generate_structured(
                prompt=prompt,
                profile=profile.llm,
                response_model=LLMPlanResponse,
            )
            result = validate_operations(result)
            result = resolve_subject_references(result, masked.entities)
            validate_entity_references(result, masked.entities)
            result = normalize_program_operations(result, masked.entities)
            logger.info("router_validated", requests=len(result.retrieval.requests))

        except PlanRejected as exc:
            logger.warning("router_invalid_output", error_type=type(exc).__name__, error=str(exc)[:500])
            result = fallback_plan(question, masked.entities)

        logger.info("router_completed", retrieval=result.retrieval.model_dump(mode="json"))
        return result
