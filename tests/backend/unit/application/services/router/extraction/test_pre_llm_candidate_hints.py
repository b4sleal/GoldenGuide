from unittest.mock import AsyncMock, Mock

import pytest

from backend.application.services.router.extraction.entity_extractor import (
    PreLLMExtractor,
)
from backend.application.services.router.extraction.matchers.course_matcher import (
    CourseCodeMatcher,
)
from backend.application.services.router.extraction.matchers.department_hint_matcher import (
    DepartmentHintMatcher,
)
from backend.application.services.router.extraction.matchers.lexicon_matcher import (
    LexiconEntityMatcher,
)
from backend.domain.entities.question import (
    DisciplineEntity,
    EntityLookup,
    EntityMatch,
    EntityType,
)
from backend.domain.entities.wlu.loris_registration import LexiconEntityType


@pytest.mark.asyncio
async def test_fuzzy_candidate_is_not_a_selected_degree():
    cache = Mock()
    cache.get_lookup_data = AsyncMock(return_value=EntityLookup(programs=["Honours BSc Psychology and Biology"]))
    resolver = Mock()
    resolver.get_aliases.side_effect = lambda kind: (
        ["psychology"] if kind in {
            LexiconEntityType.DEPARTMENT, LexiconEntityType.SUBJECT
        } else []
    )
    resolver.resolve.side_effect = lambda kind, value: (
        "Psychology" if value == "psychology" else None
    )
    resolver.resolve_course_code.return_value = None

    extractor = PreLLMExtractor(cache, [
        CourseCodeMatcher(resolver), LexiconEntityMatcher(resolver), DepartmentHintMatcher(resolver),
    ])
    masked = await extractor.extract_and_mask("course requirements for a psycho degree")

    # No degree title ranking or plan selection before the LLM; hints never mask the text.
    assert masked.text == "course requirements for a psycho degree"
    assert not any(entity.type == EntityType.PROGRAM for entity in masked.entities.values())
    assert any(
        isinstance(entity, DisciplineEntity) and entity.canonical == "Psychology" and entity.match == EntityMatch.FUZZY_HINT
        for entity in masked.entities.values()
    )
