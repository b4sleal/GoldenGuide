"""Dispatch a structured retrieval request to the SourceRetriever registered for its source."""
from collections.abc import Sequence
from typing import ClassVar, Protocol

import structlog

from backend.domain.entities.question import EntityMap
from backend.domain.entities.retrieval import Evidence
from backend.domain.entities.retrieval_plan import (
    PreLLMExtraction,
    RetrievalRequest,
    RetrievalSource,
)
from goldenguide_common.logging.trace_wrapper import traced

logger = structlog.get_logger(__name__)


class SourceRetriever(Protocol):
    """Executes structured requests for one RetrievalSource against the exact (SQL) store."""

    source: ClassVar[RetrievalSource]

    async def retrieve(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
            limit: int,
    ) -> list[Evidence]:
        ...


class StructuredRetriever:
    """Dispatch structured requests to the retriever registered for their source.

    Add a source by writing a SourceRetriever and listing it in core/di/wiring/router.py; this class
    never changes.
    """

    def __init__(self, retrievers: Sequence[SourceRetriever]):
        self.retrievers: dict[RetrievalSource, SourceRetriever] = {}
        for retriever in retrievers:
            if retriever.source in self.retrievers:
                # Two retrievers for one source would make results depend on wiring order: fail at startup.
                raise ValueError(f"Duplicate retriever for source: {retriever.source.value}")
            self.retrievers[retriever.source] = retriever

    @traced("retrieval.structured")
    async def retrieve(
            self,
            request: RetrievalRequest,
            extraction: PreLLMExtraction,
            entities: EntityMap,
            limit: int = 50,
    ) -> list[Evidence]:
        retriever = self.retrievers.get(request.source)
        if retriever is None:
            raise NotImplementedError(f"Unsupported structured source: {request.source}")

        logger.debug(
            "structured_retrieval_dispatched",
            source=request.source.value,
            operation=request.operation.value,
            retriever=type(retriever).__name__,
        )
        return await retriever.retrieve(request=request, extraction=extraction, entities=entities, limit=limit)
