"""DocumentUploadService: one blob key for upload, delete and chat links; PDFs extract to plain text."""
import io
from contextlib import asynccontextmanager

import pypdf

from backend.application.use_cases.ingestion.upload_doc import DocumentUploadService, document_blob_key
from backend.domain.entities.ingestion_types import DocType


class FakeBlob:
    def __init__(self):
        self.uploaded, self.deleted = [], []

    async def upload(self, key, data, mime_type):
        self.uploaded.append(key)

    async def delete(self, key):
        self.deleted.append(key)


class FakeKnowledge:
    def __init__(self):
        self.ingested = []

    async def ingest(self, payload):
        self.ingested.append(payload)

    async def delete_profile(self, source_id):
        pass


class FakeAppDB:
    def __init__(self):
        self.documents = self

    async def delete_document(self, document_id):
        pass

    @asynccontextmanager
    async def start(self):
        yield self


def service():
    blob, knowledge = FakeBlob(), FakeKnowledge()
    return DocumentUploadService(blob, FakeAppDB(), knowledge), blob, knowledge


async def test_upload_and_delete_use_the_same_blob_key():
    uploader, blob, knowledge = service()

    result = await uploader.upload(b"Reading week is in February.", "dates.txt", DocType.TXT)
    await uploader.delete(result["document_id"], "dates.txt", DocType.TXT)

    expected = document_blob_key(result["document_id"], "dates.txt")
    assert blob.uploaded == [expected]
    assert blob.deleted == [expected]
    assert knowledge.ingested[0].filename == "dates.txt"


async def test_pdf_without_text_is_reported_not_crashed():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    uploader, blob, _ = service()

    result = await uploader.upload(buffer.getvalue(), "scan.pdf", DocType.PDF)

    assert result == {"error": "No text could be extracted from the document."}
    assert blob.uploaded == []
