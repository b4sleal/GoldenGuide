"""Every structured source the student sees links somewhere useful."""
from backend.application.use_cases.chatbot.context_resolver import RAGContextResolver
from backend.domain.entities.retrieval import Evidence
from tests.backend.unit.application.services.router.factories import INSTITUTION

REGISTRATION_URL = str(INSTITUTION.registration_url)


async def sources_for(*records):
    # _prepare_context only uses class-level helpers; no providers are needed to build sources.
    resolver = RAGContextResolver.__new__(RAGContextResolver)
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
