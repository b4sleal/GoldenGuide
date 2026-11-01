"""AcademicRetrievalOrchestrator: listing limits, tables, truncation notes, and evidence-budget failures."""
from types import SimpleNamespace

import pytest

from backend.application.use_cases.chatbot.retrieval_orchestrator import (
    AcademicRetrievalOrchestrator,
)
from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.domain.entities.retrieval import Evidence, RetrievalStatus, TableRow
from backend.domain.entities.retrieval_plan import (
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.settings.ai_behavior import ResolvedRAGContext
from backend.domain.settings.profiles import DBEvidenceProfile, DBEvidenceSettings
from tests.backend.unit.application.services.router.factories import CS, course

SUBJECT = {"[DEPARTMENT1]": CS}
COURSE = {"[COURSE1]": course("CP104")}


def budget(max_tokens=50_000):
    return DBEvidenceProfile(
        name="test",
        detailed=DBEvidenceSettings(max_records=10, max_tokens=max_tokens),
        compact=DBEvidenceSettings(max_records=25, max_tokens=max_tokens),
        minimal=DBEvidenceSettings(max_tokens=max_tokens),
    )


def record(index):
    return Evidence(
        source_id=f"course:{index}", title=f"CP{index}", content=f"Course: CP{index}",
        table_row=TableRow(group="Computer Science courses — 2026/2027", cells={"Course": f"CP{index}"}),
    )


def section(index):
    return Evidence(
        source_id=f"course_term:{index}", title=f"CP104 — Winter 2027 — {index}", content="Full section details",
        table_row=TableRow(group="CP104 sections — Winter 2027", cells={"Section": str(index)}),
        table_content=f"Section: {index} | Open",
    )


class FakeRouter:
    def __init__(self, request, entities, carried=None):
        plan = PreLLMExtraction(retrieval=RetrievalPlan(requests=[request], semantic_fallback=False))
        self.result = (plan, entities, carried or {})

    async def route(self, question, earlier):
        return self.result


class FakeStructured:
    def __init__(self, count):
        self.count = count
        self.calls = []

    async def retrieve(self, request, extraction, entities, limit):
        self.calls.append((request.source, request.operation, limit))
        # Course terms return sections, everything else Academic Calendar courses.
        make = section if request.source == RetrievalSource.COURSE_TERMS else record
        return [make(index) for index in range(min(self.count, limit))]


class FakeRAG:
    def __init__(self, semantic_failed=False):
        self.semantic_failed = semantic_failed
        self.factual = []

    async def resolve_context(self, question, top_k, factual, semantic_enabled):
        self.factual = factual
        return ResolvedRAGContext.model_construct(
            context_text="ctx", sources=[], llm_profile=None, profile_name="test", links={}, tables=[],
            semantic_failed=self.semantic_failed,
        )


def orchestrator(request, entities, structured, profile=None, rag=None, carried=None):
    return AcademicRetrievalOrchestrator(
        query_router=FakeRouter(request, entities, carried),
        factual_retriever=structured,
        rag_context_resolver=rag or FakeRAG(),
        retrieval_router=SimpleNamespace(route_question=lambda q: SimpleNamespace(db_evidence=profile or budget())),
    )


LISTING = RetrievalRequest(source=RetrievalSource.COURSES, operation=RetrievalOperation.FILTER, entities=["[DEPARTMENT1]"])


async def test_planned_listing_returns_every_row_as_one_table():
    structured = FakeStructured(count=77)   # All CP courses, more than the 50 per-request default.

    context = await orchestrator(LISTING, SUBJECT, structured).resolve_context("Courses in computer science", TurnRecorder(), {})

    # 200 records plus one probe record that would prove more exist.
    assert structured.calls == [(RetrievalSource.COURSES, RetrievalOperation.FILTER, 201)]
    [table] = context.tables
    assert len(table.rows) == 77
    assert "{{TABLE:1}}" in context.context_text


async def test_failed_semantic_search_is_reported_as_a_limitation():
    rag = FakeRAG(semantic_failed=True)

    context = await orchestrator(LISTING, SUBJECT, FakeStructured(count=1), rag=rag).resolve_context("q", TurnRecorder(), {})

    assert "Could not check WLU documents: the data source was temporarily unavailable." in context.context_text


async def test_automatic_section_lookup_builds_a_table_shown_only_if_placed():
    lookup = RetrievalRequest(source=RetrievalSource.COURSES, operation=RetrievalOperation.LOOKUP, entities=["[COURSE1]"])
    structured = FakeStructured(count=3)

    context = await orchestrator(lookup, COURSE, structured).resolve_context("is CP104 hard", TurnRecorder(), {})

    # The planned lookup plus the automatic course-term lookup, both at the default limit (+1 probe).
    assert {limit for _, _, limit in structured.calls} == {51}
    # The sections are a table the answer can place, but not appended if it doesn't.
    [table] = context.tables
    assert table.title == "CP104 sections — Winter 2027"
    assert table.append_if_unplaced is False


async def test_planned_section_lookup_table_is_appended_if_unplaced():
    lookup = RetrievalRequest(source=RetrievalSource.COURSE_TERMS, operation=RetrievalOperation.LOOKUP, entities=["[COURSE1]"])

    context = await orchestrator(lookup, COURSE, FakeStructured(count=3)).resolve_context("CP104 this term", TurnRecorder(), {})

    [table] = context.tables
    assert table.append_if_unplaced is True


async def test_tabled_sections_reach_the_prompt_as_one_line_each():
    lookup = RetrievalRequest(source=RetrievalSource.COURSE_TERMS, operation=RetrievalOperation.LOOKUP, entities=["[COURSE1]"])
    rag = FakeRAG()

    await orchestrator(lookup, COURSE, FakeStructured(count=2), rag=rag).resolve_context("CP104 this term", TurnRecorder(), {})

    sections = [item for item in rag.factual if item.source_id.startswith("course_term:")]
    assert [item.content for item in sections] == ["Section: 0 | Open", "Section: 1 | Open"]


async def test_evidence_over_budget_is_reported_not_raised(monkeypatch):
    captured = {}

    def capture(outcomes, *args):
        captured["outcomes"] = outcomes
        return []

    monkeypatch.setattr("backend.application.use_cases.chatbot.retrieval_orchestrator.limitation_notes", capture)
    structured = FakeStructured(count=77)

    await orchestrator(LISTING, SUBJECT, structured, profile=budget(max_tokens=10)).resolve_context("q", TurnRecorder(), {})

    [outcome] = captured["outcomes"]
    assert outcome.status == RetrievalStatus.UNSUPPORTED
    assert "budget" in outcome.error


@pytest.mark.parametrize("source", [RetrievalSource.COURSE_TERMS, RetrievalSource.COURSES])
async def test_planned_filters_of_either_source_produce_tables(source):
    request = RetrievalRequest(source=source, operation=RetrievalOperation.FILTER, entities=["[DEPARTMENT1]"])

    context = await orchestrator(request, SUBJECT, FakeStructured(count=5)).resolve_context("q", TurnRecorder(), {})

    assert len(context.tables) == 1


async def test_more_matches_than_the_limit_say_search_limited():
    structured = FakeStructured(count=500)

    context = await orchestrator(LISTING, SUBJECT, structured).resolve_context("q", TurnRecorder(), {})

    [table] = context.tables
    assert len(table.rows) == 200                      # The probe record is dropped, never shown.
    assert "Search limited to 200 results for Academic Calendar course details for Computer Science" in context.context_text


async def test_exactly_the_limit_is_not_reported_as_limited():
    context = await orchestrator(LISTING, SUBJECT, FakeStructured(count=200)).resolve_context("q", TurnRecorder(), {})

    assert len(context.tables[0].rows) == 200
    assert "Search limited to 200" not in context.context_text


async def test_prompt_record_cap_says_search_limited():
    # 77 records retrieved: the table shows all, the prompt holds the first 70.
    context = await orchestrator(LISTING, SUBJECT, FakeStructured(count=77)).resolve_context("q", TurnRecorder(), {})

    assert "Search limited to 70 results: 77 records matched" in context.context_text


async def test_small_results_have_no_limit_note():
    context = await orchestrator(LISTING, SUBJECT, FakeStructured(count=5)).resolve_context("q", TurnRecorder(), {})
    assert "Search limited" not in context.context_text


EARLIER = {"[EARLIER_COURSE1]": course("CP264")}


async def test_earlier_courses_are_not_looked_up_unless_the_plan_uses_them():
    structured, recorder = FakeStructured(count=1), TurnRecorder()

    await orchestrator(LISTING, SUBJECT, structured, carried=EARLIER).resolve_context("q", recorder, {})

    assert structured.calls == [(RetrievalSource.COURSES, RetrievalOperation.FILTER, 201)]
    assert recorder.carried_entities == SUBJECT   # Unused earlier course dropped: the topic changed.


async def test_a_follow_up_that_uses_an_earlier_course_carries_it_forward():
    follow_up = RetrievalRequest(
        source=RetrievalSource.COURSE_TERMS, operation=RetrievalOperation.LOOKUP, entities=["[EARLIER_COURSE1]"],
    )
    recorder = TurnRecorder()

    await orchestrator(follow_up, {}, FakeStructured(count=1), carried=EARLIER).resolve_context("is it offered?", recorder, {})

    assert recorder.carried_entities == EARLIER
