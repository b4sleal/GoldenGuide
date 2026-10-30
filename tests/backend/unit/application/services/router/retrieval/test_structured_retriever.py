import pytest

from backend.application.services.router.retrieval.structured_retriever import (
    StructuredRetriever,
)
from backend.domain.entities.retrieval_plan import (
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)


class RecordingRetriever:
    def __init__(self, source: RetrievalSource):
        self.source = source
        self.calls = []

    async def retrieve(self, request, extraction, entities, limit):
        self.calls.append((request, extraction, entities, limit))
        return []


def request(source: RetrievalSource) -> RetrievalRequest:
    return RetrievalRequest(source=source, operation=RetrievalOperation.FILTER)


async def test_dispatches_to_the_retriever_registered_for_the_source():
    courses = RecordingRetriever(RetrievalSource.COURSES)
    pages = RecordingRetriever(RetrievalSource.WLU_PAGES)
    plan = PreLLMExtraction()

    await StructuredRetriever([courses, pages]).retrieve(request(RetrievalSource.WLU_PAGES), plan, {}, limit=7)

    assert courses.calls == []
    # Every retriever gets the same arguments, including the plan.
    assert pages.calls == [(request(RetrievalSource.WLU_PAGES), plan, {}, 7)]


async def test_unregistered_source_is_unsupported():
    retriever = StructuredRetriever([RecordingRetriever(RetrievalSource.COURSES)])
    with pytest.raises(NotImplementedError, match="Unsupported structured source"):
        await retriever.retrieve(request(RetrievalSource.COURSE_TERMS), PreLLMExtraction(), {})


def test_two_retrievers_for_one_source_fail_at_startup():
    with pytest.raises(ValueError, match="Duplicate retriever"):
        StructuredRetriever([RecordingRetriever(RetrievalSource.COURSES), RecordingRetriever(RetrievalSource.COURSES)])
