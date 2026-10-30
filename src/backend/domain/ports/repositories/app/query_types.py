"""Paging and sort options for the app repositories."""
from enum import StrEnum

from pydantic import Field

from backend.domain.entities.documents import DocumentField
from backend.domain.entities.jobs import JobBatchField, JobRunField
from backend.domain.ports.repositories.pagination import PageParams
from backend.domain.ports.repositories.sorting import SortSpec


class DocumentSortField(StrEnum):
    DOCUMENT_ID = DocumentField.DOCUMENT_ID
    CREATED_AT = DocumentField.CREATED_AT

class JobRunSortField(StrEnum):
    ID = JobRunField.ID
    STATUS = JobRunField.STATUS
    CREATED_AT = JobRunField.CREATED_AT
    STARTED_AT = JobRunField.STARTED_AT

class JobBatchSortField(StrEnum):
    ID = JobBatchField.ID
    BATCH_NO = JobBatchField.BATCH_NO
    STATUS = JobBatchField.STATUS

class DocumentPageParams(PageParams[DocumentSortField]):
    order_by: list[SortSpec[DocumentSortField]] = Field(default_factory=list)

class JobRunPageParams(PageParams[JobRunSortField]):
    order_by: list[SortSpec[JobRunSortField]] = Field(default_factory=list)

class JobBatchPageParams(PageParams[JobBatchSortField]):
    order_by: list[SortSpec[JobBatchSortField]] = Field(default_factory=list)
