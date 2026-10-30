"""Object storage port (MinIO today, S3-compatible by design)."""
from typing import Protocol


class BlobStorage(Protocol):
    async def create_bucket(self, bucket_name: str):
        ...

    async def bucket_exists(self, filename: str) -> bool:
        ...

    async def download(self, filename: str):
        ...

    async def download_many(self, keys: list[str], max_concurrency: int = 50) -> dict[str, bytes | None]:
        ...

    async def upload(self, filename: str, data: bytes, content_type: str):
        ...

    async def get_link(self, filename: str):
        ...

    async def delete(self, filename: str):
        ...