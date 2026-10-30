from unittest.mock import AsyncMock, MagicMock

from backend.application.services.router.retrieval.program_retriever import (
    ProgramRetriever,
)
from backend.domain.entities.retrieval_plan import (
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.entities.question import DisciplineEntity
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType, WluPageMetadata, WluPageRead
from tests.backend.unit.application.services.router.factories import CS, program


def retriever_returning(pages):
    repos = MagicMock()
    repos.wlu_pages.fetch_records = AsyncMock(return_value=pages)
    school_db = MagicMock()
    school_db.start.return_value.__aenter__ = AsyncMock(return_value=repos)
    school_db.start.return_value.__aexit__ = AsyncMock(return_value=None)
    return ProgramRetriever(school_db), repos


def page(id_, title, content=None):
    return WluPageRead(
        id=id_, title=title, content=content or f"{title}\n\nRequirements: CP104 and 19.5 further credits.",
        version="2026-2027", url="", site_name="academic-calendar", record_type=AcademicCalendarType.PROGRAM,
        metadata_json=WluPageMetadata(),
    )


async def lookup(retriever, entities):
    request = RetrievalRequest(
        source=RetrievalSource.WLU_PAGES, operation=RetrievalOperation.LOOKUP, entities=list(entities),
    )
    return await retriever.retrieve(request, PreLLMExtraction(), entities, limit=50)


async def discover(retriever, entities: dict[str, DisciplineEntity]):
    request = RetrievalRequest(
        source=RetrievalSource.WLU_PAGES, operation=RetrievalOperation.FILTER, entities=list(entities),
    )
    return await retriever.retrieve(request, PreLLMExtraction(), entities, limit=50)


async def test_reference_only_pages_are_not_returned():
    # The Calendar lists joint programs under both departments; one listing only points to the other.
    real = page(1, "Honours BSc Computer Science and Psychology")
    pointer = page(2, "Honours BSc Psychology and Computer Science", content=(
        "Honours BSc Psychology and Computer Science\n\n"
        "[Program](@@1@@) description link in [Computer Science and Physics](@@2@@) section."
    ))
    retriever, _ = retriever_returning([real, pointer])

    evidence = await discover(retriever, {"[DEPARTMENT1]": CS})

    assert [item.source_id for item in evidence] == ["wlu_page:1"]


async def test_lookup_fetches_identified_programs_by_id_in_one_query():
    entities = {"[PROGRAM1]": program("Computer Science BSc", 11), "[PROGRAM2]": program("Mathematics BA", 12)}
    retriever, repos = retriever_returning([page(11, "Computer Science BSc"), page(12, "Mathematics BA")])

    evidence = await lookup(retriever, entities)

    [call] = repos.wlu_pages.fetch_records.await_args_list
    query = call.kwargs["filters"]
    assert query.record_ids == [11, 12]
    assert query.record_type == AcademicCalendarType.PROGRAM
    assert query.title_contains is None
    assert [item.source_id for item in evidence] == ["wlu_page:11", "wlu_page:12"]


async def test_lookup_drops_a_record_whose_title_no_longer_matches():
    # The id now belongs to another program: citing it would answer about the wrong program.
    entities = {"[PROGRAM1]": program("Computer Science BSc", 11)}
    retriever, _ = retriever_returning([page(11, "Economics BA")])

    assert await lookup(retriever, entities) == []
