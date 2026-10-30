"""Document repository port."""
from typing import Protocol

from pydantic import BaseModel

from backend.domain.entities.documents import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
)
from backend.domain.ports.repositories.app.query_types import DocumentPageParams
from backend.domain.ports.repositories.filters import DocumentFilter
from backend.domain.ports.repositories.types import PrimaryKey


class DocumentRepository(Protocol):
    async def upsert_documents(self, documents: list[DocumentCreate]) -> list[PrimaryKey]: ...
    async def update_document(self, document_id: str, update_data: DocumentUpdate) -> None: ...
    async def fetch_documents[T: BaseModel = DocumentRead](
            self,
            page_params: DocumentPageParams,
            filters: DocumentFilter | None = None,
            *,
            view_model: type[T] = DocumentRead
    ) -> list[T]: ...
    async def delete_document(self, document_id: str) -> None: ...