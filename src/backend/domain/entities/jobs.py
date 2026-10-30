"""Tracked job runs and their batches: statuses, create/update/read models and run results."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

type JsonObject = dict[str, Any]

class FrozenJob(BaseModel):
    model_config = ConfigDict(frozen=True)


class JobMode(StrEnum):
    FRESH = "fresh"
    UPDATE = "update"
    RETRY = "retry"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobBatchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class JobWorkResult(FrozenJob):
    """Outcome of one-shot work, including an explicitly incomplete retrieval."""

    summary: JsonObject
    status: Literal[JobStatus.SUCCESS, JobStatus.PARTIAL_SUCCESS] = JobStatus.SUCCESS


class JobRunField(StrEnum):
    ID = "id"
    JOB_NAME = "job_name"
    MODE = "mode"
    STATUS = "status"
    STARTED_AT = "started_at"
    FINISHED_AT = "finished_at"
    LAST_HEARTBEAT_AT = "last_heartbeat_at"
    METADATA_JSON = "metadata_json"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class JobBatchField(StrEnum):
    ID = "id"
    RUN_ID = "run_id"
    BATCH_NO = "batch_no"
    OFFSET = "offset"
    BATCH_SIZE = "batch_size"
    STATUS = "status"
    PROCESSED_COUNT = "processed_count"
    STARTED_AT = "started_at"
    FINISHED_AT = "finished_at"
    METADATA_JSON = "metadata_json"
    ERROR_TYPE = "error_type"
    ERROR_MESSAGE = "error_message"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class JobRunBase(FrozenJob):
    job_name: str
    mode: JobMode = JobMode.FRESH
    status: JobStatus = JobStatus.QUEUED
    last_heartbeat_at: datetime | None = None
    metadata_json: JsonObject | None = None

class JobRunCreate(JobRunBase):
    pass

class JobRunUpdate(FrozenJob):
    status: JobStatus | None = None
    metadata_json: JsonObject | None = None
    started_at: datetime | None = None   # Explicitly pass the time from the Application layer
    finished_at: datetime | None = None

class JobRunRead(JobRunBase):
    id: int
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobBatchBase(FrozenJob):
    IDENTITY_FIELDS: ClassVar[tuple[JobBatchField, ...]] = (
        JobBatchField.RUN_ID,
        JobBatchField.BATCH_NO,
    )

    run_id: int
    batch_no: int = Field(ge=1)
    offset: int = Field(ge=0)
    batch_size: int = Field(ge=1)
    status: JobBatchStatus = JobBatchStatus.QUEUED
    processed_count: int | None = None
    metadata_json: JsonObject | None = None
    error_type: str | None = None
    error_message: str | None = None

class JobBatchCreate(JobBatchBase):
    pass

class JobBatchUpdate(FrozenJob):
    status: JobBatchStatus | None = None
    processed_count: int | None = None
    metadata_json: JsonObject | None = None
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

class JobBatchRead(JobBatchBase):
    id: int
    started_at: datetime | None = None
    finished_at: datetime | None = None

class JobBatchParams(FrozenJob):
    batch_no: int = Field(default=1, ge=1)
    offset: int = Field(default=0, ge=0)
    batch_size: int = Field(default=200, ge=1)


class JobBatchResult(FrozenJob):
    processed_count: int = Field(default=0, ge=0)
    metadata: JsonObject | None = None


class JobFailedBatch(FrozenJob):
    batch_no: int
    offset: int
    batch_size: int
    error_type: str
    error_message: str


class JobRunResult(FrozenJob):
    job_name: str
    run_id: int
    mode: JobMode
    status: JobStatus
    batch_size: int
    max_concurrent_batches: int
    total_rows: int
    total_batches: int
    total_processed: int
    failed_batches: list[JobFailedBatch] = Field(default_factory=list)
    audit: JsonObject | None = None
    audit_error: JsonObject | None = None
    metadata: JsonObject | None = None
    message: str | None = None

class JobRunRequest(FrozenJob):
    job_name: str
    mode: JobMode = JobMode.FRESH
    batch_size: int = Field(default=200, ge=1)
    max_concurrent_batches: int = Field(default=3, ge=1, le=20)
    metadata: JsonObject | None = None

class JobRunQueued(FrozenJob):
    run_id: int
    job_name: str
    status: JobStatus = JobStatus.QUEUED
