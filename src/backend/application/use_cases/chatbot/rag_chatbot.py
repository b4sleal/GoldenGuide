"""Answer a question: retrieve context, prompt the generation model, and stream answer events.

Events are NDJSON lines (protocol: src/backend/api/streaming.py, which adds the final "ok"/"error"):
    text      answer text
    citation  inline citation markers
    table     a table built from database records, placed where the model wrote {{TABLE:n}}
    sources   the source list, always last
"""
import json
import time
from collections.abc import AsyncGenerator

import structlog

from backend.application.use_cases.chatbot.date_scope import terms_to_cover
from backend.application.use_cases.chatbot.evidence_tables import TableMarkerParser
from backend.application.use_cases.chatbot.formatting import CitationStreamParser
from backend.application.use_cases.chatbot.link_resolver import ChatbotLinkResolver
from backend.application.use_cases.chatbot.retrieval_orchestrator import AcademicRetrievalOrchestrator, elapsed_ms
from backend.application.use_cases.settings.settings_service import SettingsService
from backend.domain.entities.wlu.academic_term import AcademicTermResolver
from backend.domain.ports.providers.llm import LLMOrchestrator

logger = structlog.get_logger()


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

    async def ask(self, question: str, top_k: int = 8) -> AsyncGenerator[str, None]:
        # Question and answer are logged at info so conversations can be reviewed; they are student
        # input, so log retention/access must be treated accordingly (see the logging configuration).
        request_started = time.perf_counter()
        logger.info("chat_question_received", question=question)

        # Step 1: retrieve everything the answer may use (records, sources, links, tables, limitations).
        retrieval_data = await self.retrieval.resolve_context(question, top_k)
        retrieval_ms = elapsed_ms(request_started)

        # Step 2: replace source URLs in the context with short placeholders the model copies back,
        # so it never retypes (or invents) long URLs; the resolver restores them in the stream.
        link_resolver = ChatbotLinkResolver()
        context_text = link_resolver.prepare_context(retrieval_data.context_text, sources=retrieval_data.sources)
        link_resolver.register_links(retrieval_data.links)

        # Step 3: build the prompt from the current runtime settings. Today's date and the date scope are
        # computed here so the answer model never works out terms itself (a saved prompt without these
        # placeholders still formats: unused keyword arguments are ignored).
        settings = await self.settings.get()
        prompt = settings.generation_llm.prompt.format(
            context_text=context_text,
            question=question,
            current_date=self.term_resolver.today().isoformat(),
            terms_to_cover=terms_to_cover(self.term_resolver),
        )
        logger.info(
            "rag_prompt_built",
            prompt_length=len(prompt),
            sources=len(retrieval_data.sources),
            tables=len(retrieval_data.tables),
            settings_version=settings.version,
        )

        # Step 4: stream post-processing chain, applied to every model chunk in this order:
        #   citations ([Source n]) -> links (placeholders -> URLs) -> tables ({{TABLE:n}} -> table event)
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

        # The answer exactly as the student sees it (after link resolution), for the completion log.
        answer_parts: list[str] = []

        def line(event: dict) -> str:
            if event["type"] == "text":
                answer_parts.append(event["text"])
            return json.dumps(event) + "\n"

        def process(events: list[dict]) -> list[str]:
            return [
                line(final)
                for event in events
                for linked in resolve_links(event)
                for final in place_tables(linked)
            ]

        # Step 5: stream the model's answer through the chain.
        generation_started = time.perf_counter()
        first_chunk_ms = None
        async for chunk in self.llm.generate_stream(prompt=prompt, profile=retrieval_data.llm_profile):
            if first_chunk_ms is None:
                first_chunk_ms = elapsed_ms(generation_started)
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

        # Step 8: the source list, always last.
        yield line({
            "type": "sources",
            "sources": [source.model_dump() for source in retrieval_data.sources],
        })

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
