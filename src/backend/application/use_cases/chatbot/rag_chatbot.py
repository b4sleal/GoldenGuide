"""Answer a question: retrieve context, prompt the generation model, and stream answer events.

Events are NDJSON lines (protocol: src/backend/api/streaming.py, which adds the final "ok"/"error"):
    status    progress before the text: understanding, searching (one per source), writing
    text      answer text
    citation  inline citation markers
    table     a table built from database records, placed where the model wrote {{TABLE:n}}
    sources   the source list, always last
"""
import asyncio
import json
import time
from collections.abc import AsyncGenerator

import structlog

from backend.application.use_cases.chatbot.date_scope import terms_to_cover
from backend.application.use_cases.chatbot.evidence_tables import TableMarkerParser
from backend.application.use_cases.chatbot.formatting import CitationStreamParser
from backend.application.use_cases.chatbot.link_resolver import ChatbotLinkResolver
from backend.application.use_cases.chatbot.retrieval_orchestrator import (
    AcademicRetrievalOrchestrator,
    elapsed_ms,
)
from backend.application.use_cases.chatbot.turn_recorder import TurnRecorder
from backend.application.use_cases.settings.settings_service import SettingsService
from backend.domain.entities.conversations import ConversationMemory
from backend.domain.entities.llm import LLMRequest, Message, MessageRole
from backend.domain.entities.turn_status import TurnStage, TurnStatus
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.ports.providers.llm import LLMOrchestrator

logger = structlog.get_logger()


def _status_line(status: TurnStatus) -> str:
    return json.dumps({"type": "status", **status.model_dump(mode="json", exclude_none=True)}) + "\n"


class RagChatbot:
    def __init__(
            self,
            context_resolver: AcademicRetrievalOrchestrator,
            llm_strategy: LLMOrchestrator,
            settings_service: SettingsService,
            term_resolver: AcademicTermResolver,
    ):
        self.retrieval = context_resolver
        self.llm = llm_strategy
        self.settings = settings_service
        self.term_resolver = term_resolver

    async def ask(
            self, question: str, recorder: TurnRecorder, memory: ConversationMemory, top_k: int = 8,
    ) -> AsyncGenerator[str]:
        """Stream the answer. `memory` is the conversation so far: earlier turns help the answer model with
        follow-ups and carried entities let the router resolve "it"; evidence and citations still come only
        from this question's retrieval."""
        # Question and answer are logged at info so conversations can be reviewed; they are student
        # input, so log retention/access must be treated accordingly (see the logging configuration).
        request_started = time.perf_counter()
        logger.info("chat_question_received", question=question)

        # Step 1: retrieve everything the answer may use (records, sources, links, tables, limitations),
        # streaming each stage's progress while it runs so the student never watches a frozen screen.
        yield _status_line(TurnStatus(stage=TurnStage.UNDERSTANDING))
        retrieval = asyncio.create_task(
            self.retrieval.resolve_context(question, recorder, memory.carried_entities, top_k)
        )
        next_status: asyncio.Future | None = None
        try:
            while not retrieval.done():
                next_status = asyncio.ensure_future(recorder.statuses.get())
                await asyncio.wait({retrieval, next_status}, return_when=asyncio.FIRST_COMPLETED)
                if next_status.done():
                    yield _status_line(next_status.result())
                else:
                    next_status.cancel()
            while not recorder.statuses.empty():
                yield _status_line(recorder.statuses.get_nowait())
        finally:
            # The student left mid-retrieval: stop the work instead of finishing it for nobody.
            retrieval.cancel()
            if next_status is not None:
                next_status.cancel()
        retrieval_data = retrieval.result()   # Raises the retrieval's own error, if it failed.
        retrieval_ms = elapsed_ms(request_started)
        recorder.timings["retrieval_ms"] = retrieval_ms

        # Step 2: keep URLs out of the context (plain course codes only, so the model never retypes, invents
        # or copies a link); the resolver links known course codes in the stream.
        link_resolver = ChatbotLinkResolver()
        context_text = link_resolver.prepare_context(retrieval_data.context_text, sources=retrieval_data.sources)
        link_resolver.register_course_links(retrieval_data.course_links)

        # Step 3: build the prompt from the current runtime settings. Today's date and the date scope are
        # computed here so the answer model never works out terms itself (a saved prompt without these
        # placeholders still formats: unused keyword arguments are ignored).
        settings = await self.settings.get()
        recorder.settings_version = settings.version
        turn = settings.generation_llm.turn.format(
            context_text=context_text,
            question=question,
            current_date=self.term_resolver.today().isoformat(),
            terms_to_cover=terms_to_cover(self.term_resolver),
        )
        logger.info(
            "rag_prompt_built",
            prompt_length=len(settings.generation_llm.system) + len(turn),
            sources=len(retrieval_data.sources),
            tables=len(retrieval_data.tables),
            settings_version=settings.version,
        )

        # Step 4: stream post-processing chain, applied to every model chunk in this order:
        #   citations ([n] or [Source n]) -> links (course codes -> URLs) -> tables ({{TABLE:n}} -> table event)
        citation_parser = CitationStreamParser(retrieval_data.sources)
        table_parser = TableMarkerParser(retrieval_data.tables)

        def resolve_links(event: dict) -> list[dict]:
            if event["type"] == "text":
                return link_resolver.feed(event["text"])
            # A citation is a boundary: release held-back link text first so ordering is kept.
            return [*link_resolver.flush(), event]

        def place_tables(event: dict) -> list[dict]:
            if event["type"] == "text":
                return table_parser.feed(event["text"])
            # Same boundary rule: release held-back text before the citation.
            return [*table_parser.flush(), event]

        # The answer exactly as the student sees it (after link resolution), recorded as it streams.
        answer_parts = recorder.answer_parts

        def line(event: dict) -> str:
            # Record exactly the resolved content being emitted, including appended/unplaced tables.
            recorder.record_answer_event(event)
            return json.dumps(event) + "\n"

        def process(events: list[dict]) -> list[str]:
            return [
                line(final)
                for event in events
                for linked in resolve_links(event)
                for final in place_tables(linked)
            ]

        # Step 5: the source list first, so inline citation chips can show their titles and previews
        # while the text streams; then the model's answer through the chain.
        yield line({
            "type": "sources",
            "sources": [source.model_dump() for source in retrieval_data.sources],
        })
        yield _status_line(TurnStatus(stage=TurnStage.WRITING))
        generation_started = time.perf_counter()
        first_chunk_ms = None
        request = LLMRequest(
            system=settings.generation_llm.system,
            messages=(*memory.earlier, Message(role=MessageRole.USER, content=turn)),
        )
        async for chunk in self.llm.generate_stream(request, profile=retrieval_data.llm_profile):
            if first_chunk_ms is None:
                first_chunk_ms = elapsed_ms(generation_started)
                recorder.timings["first_chunk_ms"] = first_chunk_ms
            for output in process(citation_parser.feed(chunk)):
                yield output

        # Step 6: end of answer, so release anything each stage still holds, in chain order.
        for output in process(citation_parser.flush()):
            yield output
        for event in link_resolver.flush():
            for final in place_tables(event):
                yield line(final)
        for event in table_parser.flush():
            yield line(event)

        # Step 7: tables the model didn't place are still shown, after the text, so none are lost.
        for event in table_parser.remaining():
            yield line(event)

        recorder.timings["generation_ms"] = elapsed_ms(generation_started)
        recorder.timings["total_ms"] = elapsed_ms(request_started)

        # Field names avoid "token": the log redactor masks any key containing it.
        logger.info(
            "chat_answer_completed",
            question=question,
            answer="".join(answer_parts),
            sources=len(retrieval_data.sources),
            retrieval_ms=retrieval_ms,                       # Routing + structured + vector search (see retrieval_timings).
            first_chunk_ms=first_chunk_ms,                   # Answer model latency until the first streamed text.
            generation_ms=elapsed_ms(generation_started),    # Whole answer generation (post-retrieval LLM).
            total_ms=elapsed_ms(request_started),            # Full round trip inside the app.
        )
