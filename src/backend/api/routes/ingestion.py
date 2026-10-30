"""Administrator endpoints that (re)build vector embeddings as tracked batch jobs.

Ingestion is separate from scraping: it re-embeds data already in Postgres, so a model or
chunking change never requires scraping WLU again. Each call records a job run, so progress and
failed batches are visible in Postgres and `mode=retry` can re-run them.

Each call queues the job and answers 202 with its run id; GET /admin/jobs/{run_id} reports the
outcome. A run of the same job still in progress is refused with 409.
"""
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request

from backend.api.auth import require_scope
from backend.api.job_runs import accepted
from backend.api.schemas import IngestionRequest, JobAccepted
from backend.application.services.jobs.job_submit import JobSubmissionService
from backend.application.use_cases.ingestion.embedding_job import EmbeddingJob
from backend.core.di.container import AppContainer
from backend.domain.entities.auth.principal import Scope

router = APIRouter(dependencies=[Depends(require_scope(Scope.INDEXING_SYNC))])


async def _submit(
        request: Request, job: EmbeddingJob, body: IngestionRequest, submission: JobSubmissionService,
) -> JobAccepted:
    queued = await submission.submit(
        job_name=job.job_name,
        mode=body.mode,
        metadata=body.model_dump(mode="json"),
        work=lambda run_id: job.run(
            run_id=run_id,
            mode=body.mode,
            batch_size=body.batch_size,
            max_concurrent_batches=body.max_concurrent_batches,
        ),
    )
    return accepted(request, queued)


@router.post("/courses/sync", status_code=202, response_model=JobAccepted)
@inject
async def ingest_courses(
        request: Request,
        body: Annotated[IngestionRequest, Query()],
        job: EmbeddingJob = Depends(Provide[AppContainer.services.course_embedding_job]),
        submission: JobSubmissionService = Depends(Provide[AppContainer.services.job_submission]),
):
    """Embed Academic Calendar course records."""
    return await _submit(request, job, body, submission)


@router.post("/course-terms/sync", status_code=202, response_model=JobAccepted)
@inject
async def ingest_course_terms(
        request: Request,
        body: Annotated[IngestionRequest, Query()],
        job: EmbeddingJob = Depends(Provide[AppContainer.services.course_term_embedding_job]),
        submission: JobSubmissionService = Depends(Provide[AppContainer.services.job_submission]),
):
    """Embed course-term (registration) records."""
    return await _submit(request, job, body, submission)


@router.post("/pages/sync", status_code=202, response_model=JobAccepted)
@inject
async def ingest_wlu_pages(
        request: Request,
        body: Annotated[IngestionRequest, Query()],
        job: EmbeddingJob = Depends(Provide[AppContainer.services.wlu_page_embedding_job]),
        submission: JobSubmissionService = Depends(Provide[AppContainer.services.job_submission]),
):
    """Embed WLU page records."""
    return await _submit(request, job, body, submission)
