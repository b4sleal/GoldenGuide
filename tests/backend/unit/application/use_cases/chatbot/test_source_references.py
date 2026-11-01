"""Consolidate only registration references, preserving citation IDs and immutable stored content."""
from datetime import UTC, datetime

import pytest

from backend.application.use_cases.chatbot.source_references import (
    normalize_history_sources,
)
from backend.domain.entities.answer_content import (
    AnswerCitationBlock,
    AnswerTableBlock,
    StoredAnswerContent,
)
from backend.domain.entities.conversations import ChatMessagePublic
from backend.domain.settings.ai_behavior import RAGSource
from tests.backend.unit.application.services.router.factories import INSTITUTION

URL = str(INSTITUTION.registration_url)
CALENDAR = RAGSource(title="Calendar", url="https://academic-calendar.wlu.ca/cp264", source_type="courses")


def message(sources, content=None):
    return ChatMessagePublic(
        id=2, position=2, role="assistant", content="Original memory text", status="complete",
        created_at=datetime.now(UTC), sources=sources, answer_content=content,
    )


def test_old_mixed_references_and_citations_are_remapped_without_mutating_saved_data():
    snapshot = StoredAnswerContent(blocks=[
        AnswerCitationBlock(source_nums=[2, 4, 3, 1], urls=[URL, URL, CALENDAR.url, CALENDAR.url]),
        AnswerTableBlock(title="Sections", columns=["Section"], rows=[["A"], ["B"]]),
    ])
    original = message([
        CALENDAR,
        RAGSource(title="Section A", url=URL, source_type="course_terms"),
        CALENDAR.model_copy(update={"title": "A distinct Calendar reference"}),
        RAGSource(title="Section B", url=URL, source_type="loris_registration"),
    ], snapshot)
    before = original.model_dump()

    public = normalize_history_sources(original, URL)

    assert [source.title for source in public.sources] == ["Calendar", "LORIS - Registration", "A distinct Calendar reference"]
    citation = public.answer_content.blocks[0]
    assert citation.source_nums == [2, 3, 1]
    assert citation.urls == [URL, CALENDAR.url, CALENDAR.url]
    assert public.answer_content.blocks[1] == snapshot.blocks[1]
    assert public.content == original.content
    assert original.model_dump() == before
    assert normalize_history_sources(public, URL) is public


@pytest.mark.parametrize("source_type", ["course_terms", "loris_registration", None])
def test_registration_titles_and_links_are_canonical_even_for_legacy_untyped_entries(source_type):
    old = message([RAGSource(title="A section", url=f"{URL}?term=202701", source_type=source_type)])
    public = normalize_history_sources(old, URL)
    assert public.sources == [RAGSource(title="LORIS - Registration", url=URL, source_type="course_terms")]
    assert public.answer_content is None


@pytest.mark.parametrize("sources", [None, [], [CALENDAR]])
def test_unrelated_or_absent_sources_are_unchanged(sources):
    original = message(sources)
    assert normalize_history_sources(original, URL) is original


def test_invalid_legacy_urls_do_not_break_history():
    original = message([RAGSource(title="Old source", url="https://[invalid")])
    assert normalize_history_sources(original, URL) is original
