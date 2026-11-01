"""Conversation repository port: conversations, their ordered messages, and per-message feedback."""
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from backend.domain.entities.conversations import (
    ChatMessageCreate,
    ChatMessageRead,
    ConversationCreate,
    ConversationRead,
    MessageFeedbackCreate,
    MessageFeedbackRead,
)
from backend.domain.ports.repositories.app.query_types import (
    ChatMessagePageParams,
    ConversationPageParams,
)
from backend.domain.ports.repositories.filters import ChatMessageFilter, ConversationFilter


class ConversationRepository(Protocol):
    async def create_conversation(self, payload: ConversationCreate) -> UUID: ...

    async def fetch_conversations[T: BaseModel = ConversationRead](
            self,
            page_params: ConversationPageParams,
            filters: ConversationFilter | None = None,
            *,
            view_model: type[T] = ConversationRead,
    ) -> list[T]: ...

    async def delete_conversations(self, filters: ConversationFilter) -> int:
        """Delete matching conversations with their messages and feedback. An empty filter is refused."""
        ...

    async def append_message(self, payload: ChatMessageCreate) -> ChatMessageRead:
        """Add the next message (position assigned here, safe under concurrent appends) and mark the
        conversation active. Raises NotFoundError for an unknown conversation."""
        ...

    async def fetch_messages[T: BaseModel = ChatMessageRead](
            self,
            page_params: ChatMessagePageParams,
            filters: ChatMessageFilter | None = None,
            *,
            view_model: type[T] = ChatMessageRead,
    ) -> list[T]: ...

    async def upsert_feedback(self, payload: MessageFeedbackCreate) -> int:
        """Record the rating for a message, replacing any earlier rating of it."""
        ...

    async def fetch_feedback(self, message_ids: Sequence[int]) -> list[MessageFeedbackRead]: ...
