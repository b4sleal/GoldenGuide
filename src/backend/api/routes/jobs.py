"""Job run status, for callers that queued a job (the endpoints answer 202 with this URL)."""
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from backend.api.auth import require_scope
from backend.api.job_runs import JOB_STATUS_ROUTE
from backend.api.schemas import JobRunStatus
from backend.core.di.container import AppContainer
from backend.domain.entities.auth.principal import Scope
from backend.domain.entities.jobs import JobRunMetadataKey, JobStatus
from backend.domain.errors import NotFoundError
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.app.query_types import JobRunPageParams
from backend.domain.ports.repositories.filters import JobRunFilter

router = APIRouter(dependencies=[Depends(require_scope(Scope.JOBS_READ))])

UNFINISHED = frozenset({JobStatus.QUEUED, JobStatus.RUNNING})

# Partial success is a finished run with some items not retrieved, not a failure.
OUTCOME_MESSAGES: dict[JobStatus, str] = {
    JobStatus.PARTIAL_SUCCESS: "Job finished, but some items could not be retrieved. See the summary for counts.",
    JobStatus.FAILED: "Job failed. Consult the server job records.",
    JobStatus.CANCELLED: "Job was cancelled before it finished.",
}


@router.get("/{run_id}", name=JOB_STATUS_ROUTE, response_model=JobRunStatus)
@inject
async def get_job_run(
        run_id: int,
        app_db: AppDB = Depends(Provide[AppContainer.persistence.app_db]),
) -> JobRunStatus:
    """Status and outcome of one run. `finished` turns true once the status is final."""
    async with app_db.start() as repos:
        runs = await repos.jobs.fetch_runs(page_params=JobRunPageParams(limit=1), filters=JobRunFilter(id=run_id))
    if not runs:
        raise NotFoundError("Job run not found")

    run = runs[0]
    # Only counts are exposed; error details of failed runs stay in server records.
    metadata = run.metadata_json or {}
    return JobRunStatus(
        run_id=run.id,
        job_name=run.job_name,
        mode=run.mode,
        status=run.status,
        finished=run.status not in UNFINISHED,
        started_at=run.started_at,
        finished_at=run.finished_at,
        last_heartbeat_at=run.last_heartbeat_at,
        message=OUTCOME_MESSAGES.get(run.status),
        summary=metadata.get(JobRunMetadataKey.SUMMARY),
        audit=metadata.get(JobRunMetadataKey.AUDIT),
    )
