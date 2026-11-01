"""Every structured source the student sees links somewhere useful."""
from uuid import uuid4

from backend.application.use_cases.chatbot.context_resolver import RAGContextResolver
from backend.application.use_cases.chatbot.formatting import CitationStreamParser
from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.domain.entities.conversations import ChatTurnContext, MessageStatus
from backend.domain.entities.retrieval import Evidence
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk
from tests.backend.unit.application.services.router.factories import INSTITUTION

REGISTRATION_URL = str(INSTITUTION.registration_url)


async def sources_for(*records):
    # _prepare_context only uses class-level helpers; no providers are needed to build sources.
    resolver = RAGContextResolver.__new__(RAGContextResolver)
    resolver.registration_url = REGISTRATION_URL
    _, sources, _ = await resolver._prepare_context(hits=[], max_chunks=0, factual=list(records))
    return sources


async def test_course_term_sources_link_to_loris_registration():
    record = Evidence(
        source_id="course_term:7", title="CP220 — Fall 2026 — A", content="Course: CP220",
        url=REGISTRATION_URL,
    )
    [source] = await sources_for(record)

    assert source.url == REGISTRATION_URL
    assert source.source_type == "course_terms"
    assert source.title == "LORIS - Registration"


async def test_course_sources_keep_their_calendar_link():
    url = "https://academic-calendar.wlu.ca/course.php?c=1"
    [source] = await sources_for(Evidence(source_id="course:1", title="CP220", content="Course: CP220", url=url))
    assert source.url == url


def test_semantic_course_url():
    payload = {
        "source_type": "wlu_page",
        "title": "Discrete Structures",
        "calendar_url": (
            "https://academic-calendar.wlu.ca/course.php?c=123"
        ),
    }

    assert RAGContextResolver._source_url(payload) == (
        "https://academic-calendar.wlu.ca/course.php?c=123"
    )


def test_unresolved_links_become_plain_text():
    text = "Prerequisite: [CP164](@@3@@) or [GENG131](@@4@@)."

    assert RAGContextResolver._clean_unresolved_links(text) == (
        "Prerequisite: [CP164] or [GENG131]."
    )


def test_invalid_source_url_is_rejected():
    assert RAGContextResolver._source_url({
        "url": "null"
    }) is None


async def test_registration_references_merge_before_generation_and_persistence_without_losing_evidence():
    resolver = RAGContextResolver.__new__(RAGContextResolver)
    resolver.registration_url = REGISTRATION_URL
    calendar_url = "https://academic-calendar.wlu.ca/cp264"
    records = [
        Evidence(source_id="course_term:1", title="CP264 section A", content="CRN: 100", url=REGISTRATION_URL),
        Evidence(source_id="course:1", title="CP264", content="Prerequisite: CP164", url=calendar_url),
        Evidence(source_id="course_term:2", title="CP264 section B", content="CRN: 200", url=REGISTRATION_URL),
    ]
    hit = RetrievedChunk(content="CRN: 300", score=1, payload={
        "source_id": "3", "source_type": "loris_registration", "title": "CP264 section C", "url": REGISTRATION_URL,
    })
    context, sources, _ = await resolver._prepare_context(hits=[hit], max_chunks=1, factual=records)

    assert [source.title for source in sources] == ["LORIS - Registration", "CP264"]
    assert [source.url for source in sources] == [REGISTRATION_URL, calendar_url]
    for crn in ("100", "200", "300"):
        assert f"CRN: {crn}" in context
    assert "SOURCE 1 (CP264 section A)" in context
    assert "SOURCE 1 (CP264 section B)" in context
    assert "SOURCE 1 (CP264 section C)" in context
    assert "SOURCE 2 (CP264)" in context

    recorder = TurnRecorder(sources=sources)
    for event in CitationStreamParser(sources).feed("Sections [Source 1, 1]; prerequisite [Source 2]."):
        recorder.record_answer_event(event)
    saved = recorder.answer_message(uuid4(), ChatTurnContext(client_id_hash="device"), MessageStatus.COMPLETE)
    assert saved.sources == [source.model_dump(mode="json") for source in sources]
    citations = [block for block in saved.answer_content.blocks if block.type == "citation"]
    assert [block.source_nums for block in citations] == [[1], [2]]
    assert [block.urls for block in citations] == [[REGISTRATION_URL], [calendar_url]]
