"""Stored chat conversations: messages with their retrieval diagnostics, and student feedback.

Diagnostics (query plan, retrieval outcomes, sources) are kept as JSON snapshots of the domain
models at the time of the answer, so old conversations stay readable after those models change.
"""
from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.domain.entities.answer_content import StoredAnswerContent
from backend.domain.entities.llm import Message, MessageRole
from backend.domain.entities.question import EntityMap
from backend.domain.settings.ai_behavior import RAGSource

type JsonObject = dict[str, Any]


class FrozenConversation(BaseModel):
    model_config = ConfigDict(frozen=True)


class MessageStatus(StrEnum):
    COMPLETE = "complete"
    ERROR = "error"              # Generation failed; content holds any text streamed before it.
    INTERRUPTED = "interrupted"  # The stream stopped without completing or reporting an error.


class FeedbackRating(StrEnum):
    UP = "up"
    DOWN = "down"


class FeedbackReason(StrEnum):
    WRONG_INFORMATION = "wrong_information"
    OUTDATED = "outdated"
    MISSING_SOURCE = "missing_source"
    DID_NOT_ANSWER = "did_not_answer"
    OTHER = "other"


class ConversationField(StrEnum):
    ID = "id"
    OWNER_SUBJECT = "owner_subject"
    CLIENT_ID_HASH = "client_id_hash"
    TITLE = "title"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class ChatMessageField(StrEnum):
    ID = "id"
    CONVERSATION_ID = "conversation_id"
    POSITION = "position"
    ROLE = "role"
    STATUS = "status"
    CREATED_AT = "created_at"


class ConversationBase(FrozenConversation):
    # Signed-in owner (identity provider subject). None while chat is anonymous.
    owner_subject: str | None = Field(default=None, min_length=1, max_length=255)
    # Hash of the anonymous device ID (never the raw cookie value), so a device can list its own chats.
    client_id_hash: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=200)


class ConversationCreate(ConversationBase):
    pass


class ConversationRead(ConversationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ChatMessageBase(FrozenConversation):
    conversation_id: UUID
    role: MessageRole
    # May be empty for an assistant message that failed before any text was streamed.
    content: str
    status: MessageStatus = MessageStatus.COMPLETE
    # None identifies legacy text-only messages. Keep content for conversation memory and old clients.
    answer_content: StoredAnswerContent | None = None

    # Assistant diagnostics, for reviewing where an answer went wrong.
    query_plan: JsonObject | None = None
    retrieval_outcomes: list[JsonObject] | None = None
    sources: list[JsonObject] | None = None
    # Entities the next question may refer back to ("is it offered in winter?"), as an EntityMap.
    carried_entities: JsonObject | None = None
    profile_name: str | None = Field(default=None, max_length=128)
    settings_version: int | None = None
    timings: dict[str, int | None] | None = None   # Milliseconds per stage, e.g. retrieval_ms, total_ms.
    trace_id: str | None = Field(default=None, max_length=32)
    request_id: str | None = Field(default=None, max_length=64)

    # Generation failure: exception type, the public error code shown to the student, internal detail.
    error_type: str | None = Field(default=None, max_length=256)
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.role is MessageRole.USER and not self.content:
            raise ValueError("A user message needs content")
        if (self.status is MessageStatus.ERROR) != (self.error_type is not None):
            raise ValueError("error_type is required for, and only for, an errored message")
        return self


class ChatMessageCreate(ChatMessageBase):
    pass


class ChatMessageRead(ChatMessageBase):
    id: int
    position: int   # 1-based order within the conversation.
    created_at: datetime


class MessageFeedbackBase(FrozenConversation):
    message_id: int
    rating: FeedbackRating
    reason: FeedbackReason | None = None
    comment: str | None = Field(default=None, min_length=1, max_length=2000)


class MessageFeedbackCreate(MessageFeedbackBase):
    pass


class MessageFeedbackRead(MessageFeedbackBase):
    id: int
    created_at: datetime
    updated_at: datetime


class ChatTurnContext(FrozenConversation):
    """Who is asking and where the turn belongs, supplied by the transport layer."""

    # Continue this conversation; None starts a new one.
    conversation_id: UUID | None = None
    # Required: conversation ownership is checked against it, so it must never be missing.
    client_id_hash: str = Field(min_length=1, max_length=64)
    request_id: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, max_length=32)


class ConversationSummary(FrozenConversation):
    """What a student sees in their history list: no owner or device details."""

    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessagePublic(FrozenConversation):
    """What a student sees of a stored message: no plan, retrieval outcomes, errors or trace IDs."""

    id: int
    position: int
    role: MessageRole
    content: str
    status: MessageStatus
    created_at: datetime
    answer_content: StoredAnswerContent | None = None
    # Typed projection exposes only public source metadata, not arbitrary diagnostic JSON fields.
    sources: list[RAGSource] | None = None


class ConversationMemory(FrozenConversation):
    """What a new question inherits from its conversation: earlier turns for the answer model, and the
    entities the previous answer carried forward for the router."""

    earlier: tuple[Message, ...] = ()
    carried_entities: EntityMap = Field(default_factory=dict)
