"""Paging and sort options for the app repositories."""
from enum import StrEnum

from pydantic import Field

from backend.domain.entities.conversations import ChatMessageField, ConversationField
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

class ConversationSortField(StrEnum):
    CREATED_AT = ConversationField.CREATED_AT
    UPDATED_AT = ConversationField.UPDATED_AT

class ChatMessageSortField(StrEnum):
    POSITION = ChatMessageField.POSITION

class DocumentPageParams(PageParams[DocumentSortField]):
    order_by: list[SortSpec[DocumentSortField]] = Field(default_factory=list)

class JobRunPageParams(PageParams[JobRunSortField]):
    order_by: list[SortSpec[JobRunSortField]] = Field(default_factory=list)

class JobBatchPageParams(PageParams[JobBatchSortField]):
    order_by: list[SortSpec[JobBatchSortField]] = Field(default_factory=list)

class ConversationPageParams(PageParams[ConversationSortField]):
    order_by: list[SortSpec[ConversationSortField]] = Field(default_factory=list)

class ChatMessagePageParams(PageParams[ChatMessageSortField]):
    order_by: list[SortSpec[ChatMessageSortField]] = Field(default_factory=list)
