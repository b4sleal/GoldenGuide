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
from backend.domain.entities.ingestion_types import VectorSource
from backend.domain.entities.job_requests import IndexingKey, IndexingParams, JobKey

router = APIRouter(dependencies=[Depends(require_scope(Scope.INDEXING_SYNC))])

Submission = Annotated[JobSubmissionService, Depends(Provide[AppContainer.services.job_submission])]


async def _submit(
        request: Request, key: IndexingKey, source: VectorSource, body: IngestionRequest,
        submission: JobSubmissionService,
) -> JobAccepted:
    queued = await submission.submit(
        job_name=EmbeddingJob.job_name_for(source),
        mode=body.mode,
        request=IndexingParams(
            key=key, mode=body.mode, batch_size=body.batch_size, max_concurrent_batches=body.max_concurrent_batches,
        ),
    )
    return accepted(request, queued)


@router.post("/courses/sync", status_code=202, response_model=JobAccepted)
@inject
async def ingest_courses(
        request: Request, body: Annotated[IngestionRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Embed Academic Calendar course records."""
    return await _submit(request, JobKey.COURSE_INDEXING, VectorSource.COURSES, body, submission)


@router.post("/course-terms/sync", status_code=202, response_model=JobAccepted)
@inject
async def ingest_course_terms(
        request: Request, body: Annotated[IngestionRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Embed course-term (registration) records."""
    return await _submit(request, JobKey.COURSE_TERM_INDEXING, VectorSource.COURSE_TERMS, body, submission)


@router.post("/pages/sync", status_code=202, response_model=JobAccepted)
@inject
async def ingest_wlu_pages(
        request: Request, body: Annotated[IngestionRequest, Query()], submission: Submission,
) -> JobAccepted:
    """Embed WLU page records."""
    return await _submit(request, JobKey.PAGE_INDEXING, VectorSource.WLU_PAGES, body, submission)
