"""Gaps in retrieval must reach the answer model instead of disappearing silently."""
import json
from types import SimpleNamespace

import pytest

from backend.application.use_cases.chatbot.retrieval_limitations import (
    SECTION_HEADING,
    context_limit_note,
    describe_request,
    limitation_notes,
    render_limitations,
)
from backend.application.use_cases.chatbot.retrieval_orchestrator import (
    AcademicRetrievalOrchestrator,
)
from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.domain.entities.retrieval import (
    Evidence,
    RetrievalOutcome,
    RetrievalStatus,
)
from backend.domain.entities.retrieval_plan import (
    GlobalFilters,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.settings.ai_behavior import ResolvedRAGContext
from tests.backend.unit.application.services.router.factories import course

ENTITIES = {"[COURSE1]": course("CP220", raw="cp220")}

WINTER_OFFERINGS = RetrievalRequest(
    source=RetrievalSource.COURSE_TERMS,
    operation=RetrievalOperation.FILTER,
    entities=["[COURSE1]"],
    filters=GlobalFilters(term=["winter"]),
)


def key(request: RetrievalRequest) -> str:
    return json.dumps(request.model_dump(mode="json", exclude={"role"}), sort_keys=True)


def outcome(request, status, count=None):
    return RetrievalOutcome(request=request, status=status, count=count, error="internal detail")


# ---- pure functions -----------------------------------------------------------------------------

def test_description_names_course_and_term_not_masks():
    assert describe_request(WINTER_OFFERINGS, ENTITIES) == (
        "LORIS course offerings (term sections) for CP220 (term: winter)"
    )


@pytest.mark.parametrize(
    ("status", "count", "expected_start"),
    [
        (RetrievalStatus.UNSUPPORTED, None, "Could not check"),
        (RetrievalStatus.FAILED, None, "Could not check"),
        (RetrievalStatus.COMPLETED, 0, "Checked"),
    ],
)
def test_planned_gaps_are_reported(status, count, expected_start):
    notes = limitation_notes([outcome(WINTER_OFFERINGS, status, count)], {key(WINTER_OFFERINGS)}, key, ENTITIES)
    assert len(notes) == 1
    assert notes[0].startswith(expected_start)
    assert "CP220 (term: winter)" in notes[0]
    # Exception text is for logs only, never for the model or the student.
    assert "internal detail" not in notes[0]


def test_planned_request_with_results_is_not_a_gap():
    notes = limitation_notes(
        [outcome(WINTER_OFFERINGS, RetrievalStatus.COMPLETED, 5)], {key(WINTER_OFFERINGS)}, key, ENTITIES
    )
    assert notes == []


def test_automatic_lookups_only_report_failures():
    auto = RetrievalRequest(source=RetrievalSource.COURSES, operation=RetrievalOperation.LOOKUP, entities=["[COURSE1]"])
    quiet = [outcome(auto, RetrievalStatus.COMPLETED, 0), outcome(auto, RetrievalStatus.UNSUPPORTED)]
    assert limitation_notes(quiet, set(), key, ENTITIES) == []
    assert len(limitation_notes([outcome(auto, RetrievalStatus.FAILED)], set(), key, ENTITIES)) == 1


def test_render_is_empty_without_notes():
    assert render_limitations([]) == ""
    assert SECTION_HEADING in render_limitations(["Checked x: no matching records were found."])


# ---- orchestrator: the "cp220 in winter?" incident --------------------------------------------

class FakeRouter:
    async def route(self, question, earlier):
        return PreLLMExtraction(retrieval=RetrievalPlan(requests=[WINTER_OFFERINGS], semantic_fallback=False)), ENTITIES, {}


class FakeStructured:
    """The planned winter filter cannot be compiled; automatic lookups return Fall data."""

    async def retrieve(self, request, extraction, entities, limit):
        if request.filters and request.filters.term:
            raise ValueError("Term and year must be provided together")
        return [Evidence(source_id=f"{request.source.value}:fall", title="CP220 Fall 2026", content="Fall 2026 sections")]


class FakeRAG:
    async def resolve_context(self, question, top_k, factual, semantic_enabled):
        text = "\n".join(record.content for record in factual)
        return ResolvedRAGContext.model_construct(context_text=text, sources=[], links={}, llm_profile=None, profile_name="test")


async def test_failed_planned_request_reaches_the_answer_context():
    orchestrator = AcademicRetrievalOrchestrator(
        query_router=FakeRouter(),
        factual_retriever=FakeStructured(),
        rag_context_resolver=FakeRAG(),
        retrieval_router=SimpleNamespace(route_question=lambda q: SimpleNamespace(db_evidence=None)),
    )
    orchestrator.db_evidence_selector = SimpleNamespace(select=lambda evidence, profile: evidence)

    context = await orchestrator.resolve_context("cp220 in winter?", TurnRecorder(), {})

    # The Fall evidence is still there, but the model is now told the winter part is unanswered.
    assert "Fall 2026 sections" in context.context_text
    assert SECTION_HEADING in context.context_text
    assert "Could not check LORIS course offerings (term sections) for CP220 (term: winter)" in context.context_text


def test_truncated_planned_request_says_search_limited():
    truncated = RetrievalOutcome(
        request=WINTER_OFFERINGS, status=RetrievalStatus.COMPLETED, count=50, truncated_at=50,
    )
    assert limitation_notes([truncated], {key(WINTER_OFFERINGS)}, key, ENTITIES) == [
        "Search limited to 50 results for LORIS course offerings (term sections) for CP220 (term: winter):"
        " more matching records exist.",
    ]


def test_truncated_automatic_request_is_not_reported():
    truncated = RetrievalOutcome(request=WINTER_OFFERINGS, status=RetrievalStatus.COMPLETED, count=50, truncated_at=50)
    assert limitation_notes([truncated], set(), key, ENTITIES) == []


def test_complete_results_are_not_limited():
    complete = RetrievalOutcome(request=WINTER_OFFERINGS, status=RetrievalStatus.COMPLETED, count=12)
    assert limitation_notes([complete], {key(WINTER_OFFERINGS)}, key, ENTITIES) == []


def test_context_limit_note():
    assert context_limit_note(shown=70, total=77) == (
        "Search limited to 70 results: 77 records matched, only the first 70 are listed above."
    )
