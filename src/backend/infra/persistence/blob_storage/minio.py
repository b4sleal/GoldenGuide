"""S3-compatible blob storage adapter (MinIO client; also works against AWS S3 with secure=True).

The MinIO SDK is synchronous, so every call runs in a worker thread.
"""
import asyncio
import io

import structlog
import urllib3
from minio import Minio

from backend.domain.settings.providers import MinIOSettings

logger = structlog.get_logger()

# Connection pool size: bulk downloads run up to ~50 requests at once (download_many).
POOL_SIZE = 200


class MinIOStorage:
    def __init__(self, settings: MinIOSettings):
        self.bucket = settings.bucket
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout.DEFAULT_TIMEOUT,
            maxsize=POOL_SIZE,
            retries=urllib3.Retry(
                total=3,
                backoff_factor=0.2,
                status_forcelist=[500, 502, 503, 504],
            ),
        )

        self.client = Minio(
            endpoint=settings.host + ":" + str(settings.port),
            access_key=settings.access_key.get_secret_value(),
            secret_key=settings.secret_key.get_secret_value(),
            secure=settings.secure,
            http_client=http_client,
        )

    async def initialize(self):
        """Create the bucket if it does not exist (provision job only)."""
        if not await asyncio.to_thread(self.client.bucket_exists, self.bucket):
            await asyncio.to_thread(
                self.client.make_bucket,
                self.bucket,
            )

    async def get_link(self, key: str) -> str:
        """Returns a temporary (presigned) download link for the frontend."""
        return await asyncio.to_thread(
            self.client.get_presigned_url,
            "GET",
            self.bucket,
            key,
        )

    async def download(self, filename: str) -> bytes:
        response = await asyncio.to_thread(
            self.client.get_object,
            self.bucket,
            filename,
        )
        # Always return the connection to the pool, even when reading fails.
        try:
            return await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()

    async def download_many(self, keys: list[str], max_concurrency: int = 50) -> dict[str, bytes | None]:
        """Download several blobs concurrently: key -> bytes, or None for a blob that failed (logged).

        A semaphore bounds concurrent requests so bulk jobs never exhaust the connection pool.
        """
        semaphore = asyncio.Semaphore(max_concurrency)
        results: dict[str, bytes | None] = {}

        async def _download_safe(key: str):
            async with semaphore:
                try:
                    results[key] = await self.download(key)
                except Exception as e:
                    logger.warning("bulk_blob_download_failed", blob_key=key, error_type=type(e).__name__, error=str(e))
                    results[key] = None

        await asyncio.gather(*[_download_safe(k) for k in set(keys)])

        return results

    async def upload(self, filename: str, data: bytes, content_type: str = "application/pdf"):
        await asyncio.to_thread(
            self.client.put_object,
            self.bucket,
            filename,
            io.BytesIO(data),
            len(data),
            content_type,
        )

        # Per object, so debug: a crawl uploads thousands.
        logger.debug("minio_upload", file=filename)

    async def delete(self, filename: str):
        """Remove an object. Errors propagate; the caller decides whether a failed delete matters."""
        await asyncio.to_thread(
            self.client.remove_object,
            self.bucket,
            filename,
        )
        logger.info("minio_delete_success", file=filename)
