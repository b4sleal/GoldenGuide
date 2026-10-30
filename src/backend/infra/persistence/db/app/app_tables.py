"""SQLAlchemy tables of the application database: documents, settings versions, job runs and batches."""
from datetime import datetime
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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