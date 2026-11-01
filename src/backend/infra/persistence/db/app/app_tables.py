"""SQLAlchemy tables of the application database: documents, settings versions, job runs and batches,
conversations with their messages and feedback."""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from backend.infra.persistence.db.column_types import JsonDoc


class AppBaseTable(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AppDocumentTable(AppBaseTable, TimestampMixin):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str] = mapped_column(String, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)


class AppSettingsTable(AppBaseTable):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class JobRun(AppBaseTable, TimestampMixin):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    job_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    metadata_json: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)

    batches: Mapped[list["JobBatch"]] = relationship(
        "JobBatch",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class JobBatch(AppBaseTable, TimestampMixin):
    __tablename__ = "job_batches"
    __table_args__ = (
        UniqueConstraint("run_id", "batch_no", name="uq_job_batches_run_batch_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    run_id: Mapped[int] = mapped_column(
        ForeignKey("job_runs.id"),
        nullable=False,
        index=True,
    )

    batch_no: Mapped[int] = mapped_column(Integer, nullable=False)
    offset: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    processed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    metadata_json: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)

    error_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["JobRun"] = relationship(
        "JobRun",
        back_populates="batches",
    )


class ConversationTable(AppBaseTable, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_subject: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)


class ChatMessageTable(AppBaseTable):
    __tablename__ = "chat_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "position", name="uq_chat_messages_conversation_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Deleted with the conversation by the database, so bulk deletes need no ORM cascade.
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Exact displayed content; nullable so existing messages retain their text-only representation.
    answer_content: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)

    query_plan: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)
    retrieval_outcomes: Mapped[list | None] = mapped_column(JsonDoc, nullable=True)
    sources: Mapped[list | None] = mapped_column(JsonDoc, nullable=True)
    carried_entities: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)
    profile_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settings_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timings: Mapped[dict | None] = mapped_column(JsonDoc, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    error_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class MessageFeedbackTable(AppBaseTable, TimestampMixin):
    __tablename__ = "message_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One rating per message; a new rating replaces it.
    message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, unique=True,
    )
    rating: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
