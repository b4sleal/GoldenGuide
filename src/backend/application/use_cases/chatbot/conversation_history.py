"""A device's own chat history: list, read, delete, and rate answers.

Every operation is scoped to the caller's device. Anything outside it is reported as not found,
so one student can never learn whether another's conversation or message exists.
"""
from uuid import UUID

from backend.application.use_cases.chatbot.source_references import (
    normalize_history_sources,
)
from backend.domain.entities.conversations import (
    ChatMessagePublic,
    ChatMessageRead,
    ConversationSummary,
    MessageFeedbackCreate,
)
from backend.domain.entities.llm import MessageRole
from backend.domain.errors import NotFoundError
from backend.domain.ports.repositories.app.app_db import AppDB, AppRepositories
from backend.domain.ports.repositories.app.query_types import (
    ChatMessagePageParams,
    ChatMessageSortField,
    ConversationPageParams,
    ConversationSortField,
)
from backend.domain.ports.repositories.filters import (
    ChatMessageFilter,
    ConversationFilter,
)
from backend.domain.ports.repositories.sorting import SortDirection, SortSpec
from backend.domain.settings.institution import InstitutionProfile

RECENT_FIRST = [SortSpec(field=ConversationSortField.UPDATED_AT, direction=SortDirection.DESC)]
IN_ORDER = [SortSpec(field=ChatMessageSortField.POSITION)]


class ConversationHistory:
    def __init__(self, app_db: AppDB, institution: InstitutionProfile):
        self.app_db = app_db
        self.registration_url = str(institution.registration_url)

    async def list_conversations(self, client_id_hash: str, limit: int, offset: int) -> list[ConversationSummary]:
        async with self.app_db.start() as repos:
            return await repos.conversations.fetch_conversations(
                ConversationPageParams(limit=limit, offset=offset, order_by=RECENT_FIRST),
                ConversationFilter(client_id_hash=client_id_hash),
                view_model=ConversationSummary,
            )

    async def messages(
            self, client_id_hash: str, conversation_id: UUID, limit: int, offset: int,
    ) -> list[ChatMessagePublic]:
        async with self.app_db.start() as repos:
            await self._require_owned(repos, client_id_hash, conversation_id)
            messages = await repos.conversations.fetch_messages(
                ChatMessagePageParams(limit=limit, offset=offset, order_by=IN_ORDER),
                ChatMessageFilter(conversation_id=conversation_id),
                view_model=ChatMessagePublic,
            )
        return [normalize_history_sources(message, self.registration_url) for message in messages]

    async def delete(self, client_id_hash: str, conversation_id: UUID) -> None:
        async with self.app_db.start() as repos:
            deleted = await repos.conversations.delete_conversations(
                ConversationFilter(id=conversation_id, client_id_hash=client_id_hash)
            )
        if not deleted:
            raise NotFoundError("Conversation not found")

    async def rate(self, client_id_hash: str, feedback: MessageFeedbackCreate) -> None:
        """Rate one of this device's answers; questions and other devices' messages are not found."""
        async with self.app_db.start() as repos:
            found = await repos.conversations.fetch_messages(
                ChatMessagePageParams(limit=1),
                ChatMessageFilter(id=feedback.message_id),
                view_model=ChatMessageRead,
            )
            if not found or found[0].role is not MessageRole.ASSISTANT:
                raise NotFoundError("Message not found")
            await self._require_owned(repos, client_id_hash, found[0].conversation_id, "Message not found")
            await repos.conversations.upsert_feedback(feedback)

    async def require_owned(self, client_id_hash: str, conversation_id: UUID) -> None:
        async with self.app_db.start() as repos:
            await self._require_owned(repos, client_id_hash, conversation_id)

    @staticmethod
    async def _require_owned(
            repos: AppRepositories, client_id_hash: str, conversation_id: UUID,
            message: str = "Conversation not found",
    ) -> None:
        owned = await repos.conversations.fetch_conversations(
            ConversationPageParams(limit=1),
            ConversationFilter(id=conversation_id, client_id_hash=client_id_hash),
            view_model=ConversationSummary,
        )
        if not owned:
            raise NotFoundError(message)
