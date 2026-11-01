"""Collects what one chat turn did, stage by stage, so it can be stored however the turn ends.

Each stage fills in its part as it finishes. A field still None means the turn never reached that
stage, which is different from a stage that ran and found nothing (an empty list).

Stages also report progress (`report`), which the chatbot streams to the student as it happens.
"""
import asyncio
from dataclasses import dataclass, field
from uuid import UUID

from pydantic import TypeAdapter

from backend.domain.entities.answer_content import (
    AnswerCitationBlock,
    AnswerContentBlock,
    AnswerTableBlock,
    AnswerTextBlock,
    StoredAnswerContent,
)
from backend.domain.entities.conversations import (
    ChatMessageCreate,
    ChatTurnContext,
    MessageStatus,
)
from backend.domain.entities.llm import MessageRole
from backend.domain.entities.question import EntityMap
from backend.domain.entities.retrieval import RetrievalOutcome
from backend.domain.entities.retrieval_plan import PreLLMExtraction
from backend.domain.entities.turn_status import TurnStatus
from backend.domain.errors import public_code
from backend.domain.settings.ai_behavior import RAGSource

ENTITY_MAP = TypeAdapter(EntityMap)

# Internal error detail kept for review; long provider responses are cut to this many characters.
MAX_ERROR_MESSAGE_LENGTH = 2000


@dataclass
class TurnRecorder:
    query_plan: PreLLMExtraction | None = None
    carried_entities: EntityMap | None = None
    retrieval_outcomes: list[RetrievalOutcome] | None = None
    sources: list[RAGSource] | None = None
    profile_name: str | None = None
    settings_version: int | None = None
    timings: dict[str, int | None] = field(default_factory=dict)
    answer_parts: list[str] = field(default_factory=list)
    answer_blocks: list[AnswerContentBlock] = field(default_factory=list)
    _text_parts: list[str] = field(default_factory=list)
    # Progress for the student, in order; read by whoever streams the answer.
    statuses: asyncio.Queue[TurnStatus] = field(default_factory=asyncio.Queue)
    _reported: set[TurnStatus] = field(default_factory=set)

    def record_answer_event(self, event: dict) -> None:
        """Record the final displayed content after citation/link/table resolution.

        Buffer adjacent text chunks to avoid storing a JSON block per streamed token. Citation and
        table boundaries flush that buffer, preserving their exact position even on interruption.
        """
        match event["type"]:
            case "text":
                self.answer_parts.append(event["text"])
                self._text_parts.append(event["text"])
            case "citation":
                self._flush_text()
                self.answer_blocks.append(AnswerCitationBlock.model_validate(event))
            case "table":
                self._flush_text()
                self.answer_blocks.append(AnswerTableBlock.model_validate(event))

    def _flush_text(self) -> None:
        if self._text_parts:
            self.answer_blocks.append(AnswerTextBlock(text="".join(self._text_parts)))
            self._text_parts.clear()

    def report(self, status: TurnStatus) -> None:
        """Announce real progress once: the same status twice would only repeat itself on screen."""
        if status not in self._reported:
            self._reported.add(status)
            self.statuses.put_nowait(status)

    def answer_message(
            self,
            conversation_id: UUID,
            context: ChatTurnContext,
            status: MessageStatus,
            error: BaseException | None = None,
    ) -> ChatMessageCreate:
        """The assistant message for this turn, with everything recorded up to the point it ended."""
        self._flush_text()
        return ChatMessageCreate(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content="".join(self.answer_parts),
            status=status,
            answer_content=StoredAnswerContent(blocks=self.answer_blocks) if self.answer_blocks else None,
            query_plan=self.query_plan.model_dump(mode="json") if self.query_plan else None,
            retrieval_outcomes=(
                None if self.retrieval_outcomes is None
                else [outcome.model_dump(mode="json") for outcome in self.retrieval_outcomes]
            ),
            sources=None if self.sources is None else [source.model_dump(mode="json") for source in self.sources],
            carried_entities=(
                None if self.carried_entities is None
                else ENTITY_MAP.dump_python(self.carried_entities, mode="json")
            ),
            profile_name=self.profile_name,
            settings_version=self.settings_version,
            timings=self.timings or None,
            trace_id=context.trace_id,
            request_id=context.request_id,
            error_type=type(error).__name__ if error else None,
            error_code=public_code(error) if error else None,
            error_message=str(error)[:MAX_ERROR_MESSAGE_LENGTH] if error else None,
        )
