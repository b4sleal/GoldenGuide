"""Startup step: initialize every configured blob storage backend (e.g. create or check MinIO buckets)."""
from collections.abc import Mapping

import structlog

from backend.application.startup.app import Initializer

logger = structlog.get_logger()


class BlobStorageInitializer:
    """Runs each blob backend's own initializer in order; the first failure stops startup."""

    def __init__(
            self,
            initializers: Mapping[str, Initializer]
    ):
        self.initializers = initializers

    async def initialize(self):
        for initializer in self.initializers.values():
            await initializer.initialize()
        logger.info("blob_storage_initialization_complete")
