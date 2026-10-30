
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from backend.application.services.router.retrieval import course_term_retriever
from backend.application.services.router.retrieval.course_term_retriever import (
    CourseTermRetriever,
)
from backend.domain.entities.retrieval_plan import (
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.ports.repositories.filters import CourseTermFilter
from tests.backend.unit.application.services.router.factories import INSTITUTION


@pytest.fixture(autouse=True)
def evidence_as_row_ids(monkeypatch):
    """Retrieval is under test here, not formatting: each record becomes its row id."""
    monkeypatch.setattr(course_term_retriever, "course_term_evidence", lambda terms, primary, registration_url: [row.id for row in terms])


@pytest.fixture
def setup_retriever():
    db = Mock()
    repos = Mock()
    repos.course_terms.fetch_course_terms = AsyncMock()

    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=repos)
    context.__aexit__ = AsyncMock(return_value=None)
    db.start.return_value = context

    compiler = Mock()
    compiler.compile.return_value = [
        CourseTermFilter(
            term_code="202609",
            subject_code="CP",
        ),
    ]

    retriever = CourseTermRetriever(
        school_db=db,
        compiler=compiler,
        institution=INSTITUTION,
    )

    return retriever, repos, compiler


def make_row(id: int):
    return Mock(
        id=id,
        term_code="202609",
        subject_code="CP",
        course_number=f"{200 + id}",
        section_code="A",
    )


def make_request():
    return RetrievalRequest(
        source=RetrievalSource.COURSE_TERMS,
        operation=RetrievalOperation.FILTER,
        entities=["[SUBJECT1]"],
    )


@pytest.mark.asyncio
async def test_course_term_pagination_fetches_multiple_pages(setup_retriever):
    retriever, repos, _compiler = setup_retriever

    retriever.PAGE_SIZE = 2

    repos.course_terms.fetch_course_terms.side_effect = [
        [make_row(1), make_row(2)],
        [make_row(3)],
    ]

    result = await retriever.retrieve(
        request=make_request(),
        extraction=PreLLMExtraction(),
        entities={},
        limit=5,
    )

    assert result == [1, 2, 3]
    assert repos.course_terms.fetch_course_terms.await_count == 2

    calls = repos.course_terms.fetch_course_terms.await_args_list
    assert calls[0].kwargs["page_params"].offset == 0
    assert calls[1].kwargs["page_params"].offset == 2


@pytest.mark.asyncio
async def test_course_term_results_stop_at_the_limit(setup_retriever):
    # More rows than the limit is not an error: the first `limit` are returned and fetching stops.
    # The orchestrator asks for limit + 1 to detect truncation ("Search limited to N results").
    retriever, repos, _compiler = setup_retriever
    retriever.PAGE_SIZE = 2

    repos.course_terms.fetch_course_terms.side_effect = [
        [make_row(1), make_row(2)],
        [make_row(3)],
    ]

    result = await retriever.retrieve(
        request=make_request(),
        extraction=PreLLMExtraction(),
        entities={},
        limit=2,
    )

    assert result == [1, 2]
    assert repos.course_terms.fetch_course_terms.await_count == 1


@pytest.mark.asyncio
async def test_course_term_limit_spans_filters(setup_retriever):
    retriever, repos, compiler = setup_retriever
    retriever.PAGE_SIZE = 5
    compiler.compile.return_value = [
        CourseTermFilter(term_code="202609", subject_code="CP"),
        CourseTermFilter(term_code="202701", subject_code="CP"),
    ]
    repos.course_terms.fetch_course_terms.side_effect = [[make_row(1), make_row(2), make_row(3)]]

    result = await retriever.retrieve(request=make_request(), extraction=PreLLMExtraction(), entities={}, limit=3)

    assert result == [1, 2, 3]
    assert repos.course_terms.fetch_course_terms.await_count == 1   # The second filter is never queried.


@pytest.mark.asyncio
async def test_course_term_pagination_deduplicates_filters(setup_retriever):
    retriever, repos, compiler = setup_retriever

    retriever.PAGE_SIZE = 5
    compiler.compile.return_value = [
        CourseTermFilter(
            term_code="202609",
            subject_code="CP",
        ),
        CourseTermFilter(
            term_code="202609",
            course_number="213",
        ),
    ]


    repos.course_terms.fetch_course_terms.side_effect = [
        [make_row(1), make_row(2)],
        [make_row(2), make_row(3)],
    ]

    result = await retriever.retrieve(
        request=make_request(),
        extraction=PreLLMExtraction(),
        entities={},
        limit=5,
    )

    assert result == [1, 2, 3]
    assert repos.course_terms.fetch_course_terms.await_count == 2


@pytest.mark.asyncio
async def test_course_term_invalid_limit(setup_retriever):
    retriever, repos, _compiler = setup_retriever

    with pytest.raises(ValueError, match="Invalid retrieval limit"):
        await retriever.retrieve(
            request=make_request(),
            extraction=PreLLMExtraction(),
            entities={},
            limit=0,
        )

    repos.course_terms.fetch_course_terms.assert_not_awaited()
