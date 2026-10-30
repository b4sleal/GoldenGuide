"""Background job timing (system.jobs in YAML): heartbeats and the sweep that fails dead runs."""
from pydantic import BaseModel, ConfigDict, Field, model_validator


class JobSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    heartbeat_seconds: float = Field(gt=0, description="How often a running job proves it is alive.")
    zombie_timeout_minutes: int = Field(gt=0, description="No sign of life for this long fails the run.")
    zombie_sweep_seconds: float = Field(gt=0, description="How often unfinished runs are checked.")

    @model_validator(mode="after")
    def heartbeats_fit_in_the_timeout(self) -> "JobSettings":
        # Several heartbeats must fit in the timeout, or one slow write would fail a healthy run.
        if self.heartbeat_seconds * 3 > self.zombie_timeout_minutes * 60:
            raise ValueError("zombie_timeout_minutes must cover at least three heartbeats")
        return self
