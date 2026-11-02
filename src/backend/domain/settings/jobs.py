"""Background job settings (system.jobs in YAML): where jobs run, heartbeats, and the sweep that fails dead runs."""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobExecutionMode(StrEnum):
    """Where submitted jobs run (docs/backend/architecture.md#background-jobs)."""
    IN_PROCESS = "in_process"   # As asyncio tasks inside the API process. Development only.
    WORKER = "worker"           # Queued (Procrastinate) and run by worker containers.


class WorkerSettings(BaseModel):
    """A worker process (python -m backend.worker)."""
    model_config = ConfigDict(frozen=True)

    concurrency: int = Field(gt=0, description="Jobs one worker process runs at the same time.")
    shutdown_graceful_timeout_seconds: float = Field(
        gt=0, description="On SIGTERM, how long running jobs may finish before they are cancelled.",
    )
    db_pool_max_size: int = Field(gt=0, description="Queue connections per process (Procrastinate's psycopg pool).")
    compute_processes: int = Field(
        gt=0, description="Child processes that parse in parallel (CPU-bound job steps); about one per worker CPU.",
    )


class JobSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution: JobExecutionMode = Field(description="Where submitted jobs run.")
    heartbeat_seconds: float = Field(gt=0, description="How often a running job proves it is alive.")
    zombie_timeout_minutes: int = Field(gt=0, description="A RUNNING run with no heartbeat for this long is failed.")
    queued_timeout_minutes: int = Field(
        gt=0, description="A run still QUEUED after this long is failed (it may wait behind other jobs until then).",
    )
    zombie_sweep_seconds: float = Field(gt=0, description="How often unfinished runs are checked.")
    worker: WorkerSettings

    @model_validator(mode="after")
    def heartbeats_fit_in_the_timeout(self) -> JobSettings:
        # Several heartbeats must fit in the timeout, or one slow write would fail a healthy run.
        if self.heartbeat_seconds * 3 > self.zombie_timeout_minutes * 60:
            raise ValueError("zombie_timeout_minutes must cover at least three heartbeats")
        # A run waiting in the queue must not be failed sooner than a silent running one.
        if self.queued_timeout_minutes < self.zombie_timeout_minutes:
            raise ValueError("queued_timeout_minutes must be at least zombie_timeout_minutes")
        return self
