"""Application-facing blob storage: delegates to the configured adapter (MinIO/S3)."""
import structlog

from backend.domain.ports.providers.blob import BlobStorage

logger = structlog.get_logger()


class AppBlobStorage:
    def __init__(self, blob_storage: BlobStorage):
        self.blob_storage = blob_storage

    async def get_link(self, key: str) -> str:
        """Returns a temporary download link for the frontend."""
        return await self.blob_storage.get_link(key)

    async def upload(self, filename: str, data: bytes, content_type: str = "application/pdf"):
        """Stores the raw artifact (PDF, HTML) for legal/backup/audit purposes."""
        await self.blob_storage.upload(filename, data, content_type)

    async def download(self, filename: str) -> bytes:
        """Downloads the raw artifact (PDF, HTML) for legal/backup/audit purposes."""
        return await self.blob_storage.download(filename)
    async def download_many(self, keys: list[str], max_concurrency: int = 50) -> dict[str, bytes | None]:
        """
        Safely downloads multiple blobs concurrently, returning a mapping of key -> bytes.
        Limits active connections using a Semaphore to prevent pool exhaustion.
        """
        return await self.blob_storage.download_many(keys, max_concurrency)

    async def delete(self, filename: str):
        """
        Removes an object from the bucket.
        """
        return await self.blob_storage.delete(filename)