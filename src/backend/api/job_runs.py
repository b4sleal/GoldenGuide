"""The 202 response of endpoints that queue a job (JobSubmissionService)."""
from fastapi import Request

from backend.api.schemas import JobAccepted
from backend.domain.entities.jobs import JobRunQueued

# Name of the status route (routes/jobs.py); its path is resolved by FastAPI, never hard-coded.
JOB_STATUS_ROUTE = "get_job_run"


def accepted(request: Request, queued: JobRunQueued) -> JobAccepted:
    """Relative status path, so it stays correct behind the proxy and tunnel."""
    return JobAccepted(
        run_id=queued.run_id,
        job_name=queued.job_name,
        status=queued.status,
        status_url=str(request.app.url_path_for(JOB_STATUS_ROUTE, run_id=queued.run_id)),
    )
