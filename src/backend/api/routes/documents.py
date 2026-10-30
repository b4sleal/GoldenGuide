"""Administrator endpoints for manually uploaded knowledge documents."""
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, UploadFile

from backend.api.auth import require_scope
from backend.api.schemas import DocumentResponse
from backend.application.use_cases.ingestion.upload_doc import DocumentUploadService
from backend.core.di.container import AppContainer
from backend.domain.entities.auth.principal import Scope
from backend.domain.ports.repositories.app.app_db import AppDB

router = APIRouter(dependencies=[Depends(require_scope(Scope.DOCUMENTS_WRITE))])

ALLOWED_EXTENSIONS = frozenset({"pdf", "txt", "md", "html"})
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB


@router.get("/", response_model=list[DocumentResponse])
@inject
async def list_documents(
        db: AppDB = Depends(Provide[AppContainer.persistence.app_db]),
):
    """List active documents."""
    async with db.start() as repos:
        return await repos.documents.find_documents()


@router.post("/upload")
@inject
async def upload_document(
        file: UploadFile,
        uploader: DocumentUploadService = Depends(Provide[AppContainer.services.document_uploader]),
):
    """Store a document and index it for retrieval."""
    # Step 1: a filename is required; its extension decides how the file is parsed.
    filename = file.filename
    if not filename:
        raise HTTPException(400, "No filename provided")

    # Step 2: accept only formats the uploader can parse.
    _, dot, extension = filename.rpartition(".")
    source_type = extension.lower() if dot else ""
    if source_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type; allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Step 3: enforce the size limit. Read one byte past the limit so "exactly 10 MiB" is
    # accepted and anything larger is rejected without loading the rest into memory.
    # (Starlette has already spooled the upload to a temp file; the reverse proxy should also
    # cap request bodies so oversized uploads are refused before reaching Python.)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File exceeds 10 MiB limit")

    # Step 4: hand off to the application layer (parse -> blob storage -> embeddings).
    # Known issue in that layer: an unreadable document returns {"error": ...} with HTTP 200
    # instead of raising InvalidInputError. It is fixed in the application-layer pass, not here.
    return await uploader.upload(content, filename, source_type)


@router.delete("/{document_id}", status_code=501)
async def delete_document(document_id: str) -> None:
    """Placeholder that says honestly it is not implemented: deletion must also remove vectors and stored objects."""
    raise HTTPException(501, "Document deletion is not implemented")
