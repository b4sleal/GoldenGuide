"""Source cards show a short plain-text preview of the first passage a source contributed."""
import pytest
from pydantic import ValidationError

from backend.application.use_cases.chatbot.context_resolver import RAGContextResolver
from backend.application.use_cases.chatbot.source_references import source_snippet
from backend.domain.entities.retrieval import Evidence
from backend.domain.ports.providers.vector_store.vector_models import RetrievedChunk
from backend.domain.settings.chat import SourceSnippetSettings
from tests.backend.unit.application.services.router.factories import INSTITUTION

REGISTRATION_URL = str(INSTITUTION.registration_url)


def resolver(max_chars=200):
    instance = RAGContextResolver.__new__(RAGContextResolver)
    instance.registration_url = REGISTRATION_URL
    instance.snippet_max_chars = max_chars
    return instance


def test_markup_is_removed_and_whitespace_collapsed():
    content = "## Contact\n\n- **Email:** [dbrown@wlu.ca](mailto:dbrown@wlu.ca)\n- Phone:   `519.884.0710`"
    assert source_snippet(content, 200) == "Contact Email: dbrown@wlu.ca Phone: 519.884.0710"


def test_long_text_is_cut_at_a_word_with_an_ellipsis_within_the_limit():
    snippet = source_snippet("alpha beta gamma delta epsilon", 14)
    assert snippet == "alpha beta…"
    assert len(snippet) <= 14 + 1


def test_text_within_the_limit_is_unchanged():
    assert source_snippet("Office hours: by appointment.", 200) == "Office hours: by appointment."


@pytest.mark.parametrize("content", ["", "   \n\t", "**", "- "])
def test_content_with_no_text_has_no_snippet(content):
    assert source_snippet(content, 200) is None


def test_one_unbroken_word_is_cut_at_the_limit():
    assert source_snippet("x" * 50, 10) == "x" * 10 + "…"


def test_snippet_limit_must_be_positive():
    with pytest.raises(ValidationError):
        SourceSnippetSettings(max_chars=0)


async def test_a_source_takes_its_snippet_from_the_first_passage_it_contributed():
    hits = [
        RetrievedChunk(content="", score=2, payload={
            "source_id": "9", "source_type": "wlu_page", "title": "Faculty", "url": "https://www.wlu.ca/a",
            "text": "First passage of the page.",
        }),
        RetrievedChunk(content="", score=1, payload={
            "source_id": "9", "source_type": "wlu_page", "title": "Faculty", "url": "https://www.wlu.ca/a",
            "text": "Second passage, not shown.",
        }),
    ]
    _, sources, _ = await resolver()._prepare_context(hits=hits, max_chunks=2)

    assert [source.snippet for source in sources] == ["First passage of the page."]


async def test_structured_records_get_a_snippet_from_their_rendered_evidence():
    record = Evidence(
        source_id="course:1", title="CP220", content="Course: CP220\nCredits: 0.5",
        url="https://academic-calendar.wlu.ca/course.php?c=1",
    )
    _, [source], _ = await resolver()._prepare_context(hits=[], max_chunks=0, factual=[record])

    assert source.snippet == "Course: CP220 Credits: 0.5"


async def test_the_shared_registration_source_has_no_snippet():
    record = Evidence(source_id="course_term:7", title="CP220 A", content="CRN: 100", url=REGISTRATION_URL)
    _, [source], _ = await resolver()._prepare_context(hits=[], max_chunks=0, factual=[record])

    assert source.snippet is None
