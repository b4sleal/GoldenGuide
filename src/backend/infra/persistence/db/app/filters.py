"""Translate application filter models into SQLAlchemy WHERE clauses."""
from __future__ import annotations

from sqlalchemy import Delete, Select

from backend.domain.ports.repositories.filters import (
    ChatMessageFilter,
    ConversationFilter,
    DocumentFilter,
    JobBatchFilter,
    JobRunFilter,
)
from backend.infra.persistence.db.app.app_tables import (
    AppDocumentTable,
    ChatMessageTable,
    ConversationTable,
    JobBatch,
    JobRun,
)


class JobRunFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: JobRunFilter | None) -> Select:
        if filters is None:
            return stmt

        if filters.id is not None:
            stmt = stmt.where(JobRun.id == filters.id)

        if filters.job_name is not None:
            stmt = stmt.where(JobRun.job_name == filters.job_name)

        if filters.statuses is not None:
            stmt = stmt.where(
                JobRun.status.in_([status.value for status in filters.statuses])
            )

        return stmt


class JobBatchFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: JobBatchFilter | None) -> Select:
        if filters is None:
            return stmt

        if filters.run_id is not None:
            stmt = stmt.where(JobBatch.run_id == filters.run_id)

        if filters.batch_no is not None:
            stmt = stmt.where(JobBatch.batch_no == filters.batch_no)

        if filters.statuses is not None:
            stmt = stmt.where(JobBatch.status.in_(filters.statuses))

        if filters.status is not None:
            stmt = stmt.where(JobBatch.status == filters.status.value)

        return stmt

class DocumentFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: DocumentFilter | None) -> Select:
        if filters is None:
            return stmt

        if filters.active is not None:
            stmt = stmt.where(AppDocumentTable.active == filters.active)

        if filters.source_type is not None:
            stmt = stmt.where(AppDocumentTable.source_type == filters.source_type)

        if filters.document_ids is not None:
            stmt = stmt.where(AppDocumentTable.document_id.in_(filters.document_ids))

        return stmt


class ConversationFilterTranslator:
    @staticmethod
    def apply[S: (Select, Delete)](stmt: S, filters: ConversationFilter | None) -> S:
        if filters is None:
            return stmt

        if filters.id is not None:
            stmt = stmt.where(ConversationTable.id == filters.id)

        if filters.owner_subject is not None:
            stmt = stmt.where(ConversationTable.owner_subject == filters.owner_subject)

        if filters.client_id_hash is not None:
            stmt = stmt.where(ConversationTable.client_id_hash == filters.client_id_hash)

        if filters.updated_before is not None:
            stmt = stmt.where(ConversationTable.updated_at < filters.updated_before)

        return stmt


class ChatMessageFilterTranslator:
    @staticmethod
    def apply(stmt: Select, filters: ChatMessageFilter | None) -> Select:
        if filters is None:
            return stmt

        if filters.id is not None:
            stmt = stmt.where(ChatMessageTable.id == filters.id)

        if filters.conversation_id is not None:
            stmt = stmt.where(ChatMessageTable.conversation_id == filters.conversation_id)

        if filters.statuses is not None:
            stmt = stmt.where(ChatMessageTable.status.in_([status.value for status in filters.statuses]))

        return stmt
