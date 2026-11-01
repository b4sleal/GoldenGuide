"""SQL conversation repository: conversations, race-safe message ordering, and one rating per message."""
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.entities.conversations import (
    ChatMessageCreate,
    ChatMessageField,
    ChatMessageRead,
    ConversationCreate,
    ConversationField,
    ConversationRead,
    MessageFeedbackCreate,
    MessageFeedbackRead,
)
from backend.domain.errors import InvalidInputError, NotFoundError
from backend.domain.ports.repositories.app.query_types import (
    ChatMessagePageParams,
    ConversationPageParams,
)
from backend.domain.ports.repositories.filters import ChatMessageFilter, ConversationFilter
from backend.infra.persistence.db.app.app_tables import (
    ChatMessageTable,
    ConversationTable,
    MessageFeedbackTable,
)
from backend.infra.persistence.db.app.filters import (
    ChatMessageFilterTranslator,
    ConversationFilterTranslator,
)
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.utils.generic.db_ops import (
    extract_payload,
    generic_fetch,
)
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting
from backend.infra.persistence.db.utils.generic.update_rules import overwrite

# Feedback columns a new rating replaces; message_id is the conflict key.
FEEDBACK_UPDATE_COLUMNS = ("rating", "reason", "comment")


class SqlConversationRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps) -> None:
        self.session = session
        self.dialect = dialect
        self.aliases: dict[str, InstrumentedAttribute] = {}

    # ==========================================
    # CONVERSATIONS
    # ==========================================
    async def create_conversation(self, payload: ConversationCreate) -> UUID:
        row = ConversationTable(**extract_payload(payload, self.aliases))

        self.session.add(row)
        await self.session.flush()
        return row.id

    async def fetch_conversations[T: BaseModel = ConversationRead](
            self,
            page_params: ConversationPageParams,
            filters: ConversationFilter | None = None,
            *,
            view_model: type[T] = ConversationRead,
    ) -> list[T]:
        stmt = ConversationFilterTranslator.apply(select(ConversationTable), filters)
        stmt = apply_sorting(
            stmt=stmt, model=ConversationTable, order_by=page_params.order_by,
            aliases=self.aliases, stable_tiebreaker=ConversationField.ID.value,
        )
        return await generic_fetch(self.session, stmt, ConversationTable, view_model, page_params, self.aliases)

    async def delete_conversations(self, filters: ConversationFilter) -> int:
        # An empty filter would delete every student's history.
        if filters.is_empty():
            raise InvalidInputError("Refusing to delete conversations without a filter")

        stmt = ConversationFilterTranslator.apply(delete(ConversationTable), filters)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return cast(CursorResult, result).rowcount or 0

    # ==========================================
    # MESSAGES
    # ==========================================
    async def append_message(self, payload: ChatMessageCreate) -> ChatMessageRead:
        # Locking the conversation row serializes appends, so two concurrent messages can't take the
        # same position; the unique constraint backs this up.
        locked = await self.session.execute(
            select(ConversationTable.id).where(ConversationTable.id == payload.conversation_id).with_for_update()
        )
        if locked.scalar_one_or_none() is None:
            raise NotFoundError(f"Conversation {payload.conversation_id} does not exist")

        last_position = await self.session.scalar(
            select(func.coalesce(func.max(ChatMessageTable.position), 0))
            .where(ChatMessageTable.conversation_id == payload.conversation_id)
        )
        row = ChatMessageTable(**extract_payload(payload, self.aliases), position=(last_position or 0) + 1)
        self.session.add(row)

        # Last activity drives the history order and the retention period.
        await self.session.execute(
            update(ConversationTable)
            .where(ConversationTable.id == payload.conversation_id)
            .values(updated_at=func.now())
        )
        await self.session.flush()
        await self.session.refresh(row)
        return ChatMessageRead.model_validate(row, from_attributes=True)

    async def fetch_messages[T: BaseModel = ChatMessageRead](
            self,
            page_params: ChatMessagePageParams,
            filters: ChatMessageFilter | None = None,
            *,
            view_model: type[T] = ChatMessageRead,
    ) -> list[T]:
        stmt = ChatMessageFilterTranslator.apply(select(ChatMessageTable), filters)
        stmt = apply_sorting(
            stmt=stmt, model=ChatMessageTable, order_by=page_params.order_by,
            aliases=self.aliases, stable_tiebreaker=ChatMessageField.ID.value,
        )
        return await generic_fetch(self.session, stmt, ChatMessageTable, view_model, page_params, self.aliases)

    # ==========================================
    # FEEDBACK
    # ==========================================
    async def upsert_feedback(self, payload: MessageFeedbackCreate) -> int:
        [feedback_id] = await self.dialect.upsert(
            self.session,
            table=MessageFeedbackTable.__table__,
            rows=[extract_payload(payload, self.aliases)],
            conflict_columns=["message_id"],
            # ON CONFLICT bypasses the ORM's onupdate, so updated_at is set explicitly.
            build_updates=lambda existing, incoming: {
                **overwrite(incoming, FEEDBACK_UPDATE_COLUMNS), "updated_at": func.now(),
            },
        )
        return cast(int, feedback_id)

    async def fetch_feedback(self, message_ids: Sequence[int]) -> list[MessageFeedbackRead]:
        rows = await self.session.scalars(
            select(MessageFeedbackTable).where(MessageFeedbackTable.message_id.in_(message_ids))
        )
        return [MessageFeedbackRead.model_validate(row, from_attributes=True) for row in rows]
