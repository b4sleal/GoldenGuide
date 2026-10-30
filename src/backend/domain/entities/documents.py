"""Uploaded admin documents: create/update/read models and their field names."""
from enum import StrEnum
from typing import ClassVar
from pydantic import BaseModel, ConfigDict

class FrozenDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

class DocumentField(StrEnum):
    DOCUMENT_ID = "document_id"
    SOURCE_TYPE = "source_type"
    SOURCE_REF = "source_ref"
    CONTENT_HASH = "content_hash"
    ACTIVE = "active"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

class DocumentBase(FrozenDocument):
    IDENTITY_FIELDS: ClassVar[tuple[DocumentField, ...]] = (
        DocumentField.DOCUMENT_ID,
    )
    document_id: str
    source_type: str
    source_ref: str
    content_hash: str
    active: bool = True

class DocumentCreate(DocumentBase): pass

class DocumentUpdate(FrozenDocument):
    model_config = ConfigDict(frozen=True, extra="forbid")
    active: bool | None = None

class DocumentRead(DocumentBase): pass