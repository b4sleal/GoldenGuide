"""One stored chat turn: the question is saved before answering, the answer however the stream ends.

Continuing a conversation sends its last completed question/answer pairs to the answer model, so
follow-up questions make sense. Earlier answers are context for meaning only: retrieval runs again
for every question, so evidence and citations always come from fresh sources.

History is diagnostic, not critical: if loading or saving it fails, the student still gets the answer
and the failure is logged once. An unknown or foreign conversation is still refused (NotFoundError).
"""
import asyncio
from collections.abc import AsyncGenerator
from itertools import pairwise
from uuid import UUID

import structlog
from pydantic import ValidationError

from backend.application.use_cases.chatbot.conversation_history import (
    ConversationHistory,
)
from backend.application.use_cases.chatbot.rag_chatbot import RagChatbot
from backend.application.use_cases.chatbot.turn_recorder import ENTITY_MAP, TurnRecorder
from backend.domain.entities.conversations import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatTurnContext,
    ConversationCreate,
    ConversationMemory,
    MessageStatus,
)
from backend.domain.entities.llm import Message, MessageRole
from backend.domain.entities.question import EntityMap
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.app.query_types import (
    ChatMessagePageParams,
    ChatMessageSortField,
)
from backend.domain.ports.repositories.filters import ChatMessageFilter
from backend.domain.ports.repositories.sorting import SortDirection, SortSpec
from backend.domain.settings.chat import ConversationHistorySettings

logger = structlog.get_logger()

# A new conversation is titled with the start of its first question.
TITLE_LENGTH = 80

NEWEST_FIRST = [SortSpec(field=ChatMessageSortField.POSITION, direction=SortDirection.DESC)]
# Messages read per wanted turn: a turn is two messages, doubled to leave room for failed turns skipped.
MESSAGES_READ_PER_TURN = 4


def conversation_memory(messages: list[ChatMessageRead], settings: ConversationHistorySettings) -> ConversationMemory:
    """What the next question inherits: the last completed question/answer pairs (oldest first, each
    message cut to the configured length) and the entities the latest completed answer carried forward.

    A question whose answer failed or was interrupted is left out with it: the model should not continue
    from an answer the student never fully received.
    """
    pairs = [
        (question, answer) for question, answer in pairwise(messages)
        if question.role is MessageRole.USER and answer.role is MessageRole.ASSISTANT
        and answer.status is MessageStatus.COMPLETE and answer.content
    ]
    recent = pairs[-settings.max_turns:] if settings.max_turns else []
    limit = settings.max_chars_per_message
    return ConversationMemory(
        earlier=tuple(
            Message(role=message.role, content=message.content[:limit]) for pair in recent for message in pair
        ),
        carried_entities=_carried(recent[-1][1]) if recent else {},
    )


def _carried(answer: ChatMessageRead) -> EntityMap:
    if answer.carried_entities is None:
        return {}
    try:
        return ENTITY_MAP.validate_python(answer.carried_entities)
    except ValidationError as exc:
        # Stored before an entity model changed: continue without carried entities rather than fail.
        logger.warning("carried_entities_unreadable", message_id=answer.id, error=str(exc)[:500])
        return {}


class ChatTurn:
    def __init__(
            self, chatbot: RagChatbot, app_db: AppDB, history: ConversationHistory,
            history_settings: ConversationHistorySettings,
    ):
        self.chatbot = chatbot
        self.app_db = app_db
        self.history = history
        self.history_settings = history_settings
        # Final saves run as tasks that outlive a disconnected stream; asyncio keeps only weak references.
        self._saving: set[asyncio.Task] = set()

    async def start(self, question: str, context: ChatTurnContext) -> tuple[UUID | None, AsyncGenerator[str]]:
        """Save the question, then return its conversation (None if history is unavailable) and the answer stream."""
        if context.conversation_id is not None:
            await self.history.require_owned(context.client_id_hash, context.conversation_id)

        # Read before saving the new question, so it isn't its own history.
        memory = await self._memory(context)
        conversation_id = await self._save_question(question, context)
        return conversation_id, self._answer(question, memory, context, conversation_id)

    async def _memory(self, context: ChatTurnContext) -> ConversationMemory:
        if context.conversation_id is None or self.history_settings.max_turns == 0:
            return ConversationMemory()
        try:
            async with self.app_db.start() as repos:
                recent = await repos.conversations.fetch_messages(
                    ChatMessagePageParams(
                        limit=self.history_settings.max_turns * MESSAGES_READ_PER_TURN, order_by=NEWEST_FIRST,
                    ),
                    ChatMessageFilter(conversation_id=context.conversation_id),
                    view_model=ChatMessageRead,
                )
        except Exception as exc:
            logger.error("chat_history_load_failed", error_type=type(exc).__name__, exc_info=exc)
            return ConversationMemory()
        return conversation_memory(list(reversed(recent)), self.history_settings)

    async def _save_question(self, question: str, context: ChatTurnContext) -> UUID | None:
        try:
            async with self.app_db.start() as repos:
                conversation_id = context.conversation_id or await repos.conversations.create_conversation(
                    ConversationCreate(client_id_hash=context.client_id_hash, title=question[:TITLE_LENGTH])
                )
                await repos.conversations.append_message(ChatMessageCreate(
                    conversation_id=conversation_id, role=MessageRole.USER, content=question,
                    request_id=context.request_id, trace_id=context.trace_id,
                ))
            return conversation_id
        except Exception as exc:
            logger.error("chat_history_save_failed", stage="question", error_type=type(exc).__name__, exc_info=exc)
            return None

    async def _answer(
            self, question: str, memory: ConversationMemory, context: ChatTurnContext,
            conversation_id: UUID | None,
    ) -> AsyncGenerator[str]:
        recorder = TurnRecorder()
        # Cancellation and closing the generator (student disconnected) are BaseExceptions: interrupted.
        status, error = MessageStatus.INTERRUPTED, None
        try:
            async for line in self.chatbot.ask(question, recorder, memory):
                yield line
            status = MessageStatus.COMPLETE
        except Exception as exc:
            status, error = MessageStatus.ERROR, exc
            raise
        finally:
            if conversation_id is not None:
                await self._save_answer(recorder.answer_message(conversation_id, context, status, error))

    async def _save_answer(self, message: ChatMessageCreate) -> None:
        # A disconnect cancels the stream, and an await in its finally block would be cancelled too.
        # The save runs as its own task: shielded from that cancellation, it completes regardless.
        task = asyncio.create_task(self._append_answer(message))
        self._saving.add(task)
        task.add_done_callback(self._saving.discard)
        # If cancelled while waiting, the cancellation still propagates; only the save is protected.
        await asyncio.shield(task)

    async def _append_answer(self, message: ChatMessageCreate) -> None:
        try:
            async with self.app_db.start() as repos:
                await repos.conversations.append_message(message)
        except Exception as exc:
            logger.error(
                "chat_history_save_failed", stage="answer", status=message.status,
                error_type=type(exc).__name__, exc_info=exc,
            )
