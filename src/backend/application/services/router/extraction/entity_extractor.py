"""Run the configured entity matchers over a question and return the masked text plus extracted entities."""
from collections import Counter
from collections.abc import Sequence

import structlog

from backend.application.services.router.extraction.entity_lookup_cache import (
    EntityLookupCache,
)
from backend.application.services.router.extraction.matchers.base import (
    EntityMatcher,
    MaskingState,
)
from backend.domain.entities.question import (
    DisciplineEntity,
    EntityMatch,
    MaskedQuestion,
)
from goldenguide_common.logging.trace_wrapper import traced

logger = structlog.get_logger(__name__)


class PreLLMExtractor:
    """Replaces recognized entities in the question with masks ("[COURSE1]") and returns their data.

    Each EntityMatcher handles one entity kind, in order (see core/di/wiring/router.py). Recognize
    a new kind by adding a matcher there; this class never changes. No hardcoded program titles or
    degree/major keyword analyzer.
    """

    def __init__(self, entity_cache: EntityLookupCache, matchers: Sequence[EntityMatcher]):
        self.entity_cache = entity_cache
        self.matchers = tuple(matchers)

    @traced("router.extract")
    async def extract_and_mask(self, user_query: str) -> MaskedQuestion:
        lookup = await self.entity_cache.get_lookup_data()
        state = MaskingState(text=user_query)

        for matcher in self.matchers:
            before = len(state.entities)
            matcher.apply(state, lookup)
            # Which matcher claimed what: the first thing to check when a question is routed wrong.
            logger.debug(
                "router_matcher_applied",
                matcher=type(matcher).__name__,
                masks=list(state.entities)[before:],
            )

        # Types and counts only: raw entity text (names, rooms) stays out of info logs.
        logger.info(
            "router_entities_extracted",
            entities=sorted(state.entities),
            types=dict(Counter(entity.type.value for entity in state.entities.values())),
            fuzzy_hints=sum(
                isinstance(entity, DisciplineEntity) and entity.match == EntityMatch.FUZZY_HINT
                for entity in state.entities.values()
            ),
        )
        return MaskedQuestion(text=state.text, entities=state.entities)
