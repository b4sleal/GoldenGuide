"""Retrieve Academic Calendar program pages: discover by discipline (FILTER) or load by id (LOOKUP)."""
import structlog

from backend.application.services.router.evidence.program_evidence import (
    program_evidence,
)
from backend.domain.entities.question import (
    SUBJECT_TYPES,
    DisciplineEntity,
    EntityMap,
    ProgramEntity,
)
from backend.domain.entities.retrieval import Evidence
from backend.domain.entities.retrieval_plan import (
    EvidenceRole,
    PreLLMExtraction,
    RetrievalOperation,
    RetrievalRequest,
    RetrievalSource,
)
from backend.domain.entities.wlu.wlu_pages import AcademicCalendarType
from backend.domain.ports.repositories.filters import WluPageFilter
from backend.domain.ports.repositories.school.query_types import WluPageParams
from backend.domain.ports.repositories.school.school_db import SchoolDB

logger = structlog.get_logger(__name__)

MAX_PAGES = 50
MAX_LIMIT = 250


class ProgramRetriever:
    """Discover Academic Calendar programs or load their requirements.

    FILTER discovers program records from canonical academic entities.
    LOOKUP resolves a specific program record chosen from discovery.
    """

    source = RetrievalSource.WLU_PAGES

    def __init__(self, school_db: SchoolDB):
        self.school_db = school_db

    async def retrieve(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
            limit: int,
    ) -> list[Evidence]:
        # `extraction` is part of the SourceRetriever contract; program queries need only the request.
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError("Invalid program retrieval limit")
        if not request.entities:
            raise ValueError("Program retrieval requires entities")
        unknown = [mask for mask in request.entities if mask not in entities]
        if unknown:
            raise ValueError(f"Unknown entity: {unknown[0]}")

        selected = [entities[mask] for mask in request.entities]

        if request.operation == RetrievalOperation.FILTER:
            pages = await self.discover(selected, request, limit)
        elif request.operation == RetrievalOperation.LOOKUP:
            pages = await self.lookup(selected, limit)
        else:
            raise NotImplementedError(f"Unsupported program operation: {request.operation}")

        # Cross-listing stubs that only point to another entry have nothing to answer with. They are
        # dropped here, before they become evidence, sources, or program entities for follow-up lookups.
        references = sum(page.is_reference_only for page in pages)
        pages = [page for page in pages if not page.is_reference_only]

        logger.info(
            "program_retrieval_completed", operation=request.operation.value, records=len(pages),
            reference_pages_skipped=references,
        )
        primary = request.role == EvidenceRole.REQUIRED
        return [program_evidence(page, primary) for page in pages]

    async def discover(self, selected: list, request: RetrievalRequest, limit: int) -> list:
        """Programs whose titles contain the disciplines' canonical names (all of them, or any)."""
        if not all(isinstance(item, DisciplineEntity) and item.type in SUBJECT_TYPES for item in selected):
            raise ValueError("Discovery requires academic disciplines")

        query_filter = WluPageFilter(
            record_type=AcademicCalendarType.PROGRAM,
            title_terms=list(dict.fromkeys(item.canonical for item in selected)),
            title_operator=request.entity_operator,
            has_content=True,
        )
        async with self.school_db.start() as repos:
            return await repos.wlu_pages.fetch_records(
                page_params=WluPageParams(limit=min(limit, MAX_PAGES)),
                filters=query_filter,
            )

    async def lookup(self, selected: list, limit: int) -> list:
        """Exactly the identified programs, by record id (ids disambiguate identical titles across calendars).

        One query for all of them. A record whose title no longer matches the entity is dropped: the id
        was reused or the program renamed, and serving it would cite the wrong program.
        """
        if not all(isinstance(item, ProgramEntity) for item in selected):
            raise ValueError("Lookup requires program entities")

        expected = {item.record_id: item.canonical.casefold() for item in selected}
        async with self.school_db.start() as repos:
            pages = await repos.wlu_pages.fetch_records(
                page_params=WluPageParams(limit=min(limit, MAX_PAGES, len(expected))),
                filters=WluPageFilter(
                    record_type=AcademicCalendarType.PROGRAM,
                    record_ids=sorted(expected),
                    has_content=True,
                ),
            )
        return [page for page in pages if expected.get(page.id) == page.title.casefold()]
