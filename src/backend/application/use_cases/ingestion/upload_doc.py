"""Admin document upload: extract text, store the original file, embed the text; and the matching delete.

The document id is a hash of the extracted text, so re-uploading the same content replaces its vectors.
A failure after the blob upload rolls back what was stored (best effort) before the error propagates.
"""
import asyncio
import io

import pypdf
import structlog

from backend.application.use_cases.ingestion.ingest_knowledge import KnowledgeIngestor
from backend.domain.entities.ingestion_types import KnowledgeSourceType, DocMimeType, DocumentVectorPayload, DocType, VectorSource
from backend.domain.ports.providers.blob import BlobStorage
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.shared.utils.hashing import compute_uuid

logger = structlog.get_logger()


def document_blob_key(document_id: str, filename: str) -> str:
    """Where an uploaded document's original file is stored. The one definition used to upload, delete
    and link it (the chat context links uploaded documents by this key)."""
    return f"{KnowledgeSourceType.DOC.value}/{document_id}/{filename}"


class DocumentUploadService:
    def __init__(
            self,
            blob_storage: BlobStorage,
            app_db: AppDB,
            knowledge_service: KnowledgeIngestor,
    ):
        self.blob_storage = blob_storage
        self.app_db = app_db
        self.knowledge_service = knowledge_service

    async def upload(self, file_bytes: bytes, filename: str, doc_type: str):
        doc_id = None

        try:
            mime_type = DocMimeType.TXT
            if doc_type == DocType.PDF:
                raw_text = await asyncio.to_thread(self._extract_pdf_text, file_bytes)
            else:
                raw_text = file_bytes.decode("utf-8", errors="ignore")

            match doc_type:
                case DocType.TXT:
                    mime_type = DocMimeType.TXT
                case DocType.HTML:
                    mime_type = DocMimeType.HTML
                case DocType.MARKDOWN:
                    mime_type = DocMimeType.MARKDOWN
                case DocType.PDF:
                    mime_type = DocMimeType.PDF

            if not raw_text.strip():
                return {"error": "No text could be extracted from the document."}

            doc_id = compute_uuid(raw_text)

            await self.blob_storage.upload(document_blob_key(doc_id, filename), file_bytes, mime_type)

            await self.knowledge_service.ingest(
                DocumentVectorPayload(
                    content=raw_text,
                    source_id=doc_id,
                    embedding_source=VectorSource.DOCUMENTS,
                    source_type=KnowledgeSourceType.DOC,
                    record_type=doc_type,
                    doc_type=doc_type,
                    filename=filename,
                    mime_type=mime_type,
                )
            )

            return {"document_id": doc_id}

        except Exception as e:
            logger.warning(
                "upload_failed",
                doc_id=doc_id,
                filename=filename,
                source_type=doc_type,
                error_type=type(e).__name__,
                error=str(e),
            )

            if doc_id is not None:
                try:
                    await self.delete(doc_id, filename, doc_type)
                except Exception as cleanup_error:
                    logger.warning(
                        "upload_cleanup_failed",
                        doc_id=doc_id,
                        filename=filename,
                        source_type=doc_type,
                        error=str(cleanup_error),
                    )

            raise

    async def delete(self, document_id: str, filename: str, source_type: str):
        """Remove a document's vectors, stored file and row. `source_type` is kept for callers; the key no longer uses it."""
        await self.knowledge_service.delete_profile(document_id)
        await self.blob_storage.delete(document_blob_key(document_id, filename))

        async with self.app_db.start() as repos:
            await repos.documents.delete_document(document_id)

        logger.info("document_deleted", document_id=document_id)

    def _extract_pdf_text(self, file_bytes: bytes) -> str:
        """All extractable page text, one page per line block (scanned pages without a text layer give nothing)."""
        pdf_stream = io.BytesIO(file_bytes)
        reader = pypdf.PdfReader(pdf_stream)

        extracted_text: list[str] = []

        for page in reader.pages:
            content = page.extract_text()
            if content:
                extracted_text.append(content)

        return "\n".join(extracted_text)