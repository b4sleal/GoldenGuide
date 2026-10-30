"""Run a list of startup steps in order, stopping at the first failure."""
from typing import Protocol

import structlog

logger = structlog.get_logger(__name__)


class Initializer(Protocol):
    async def initialize(self) -> None: ...


class AppStartup:
    """Runs initializers sequentially. Used twice (see core/di/wiring/startup.py):
    the API's read-only checks, and the provision job's create-if-missing steps."""

    def __init__(self, initializers: list[Initializer]):
        self.initializers = initializers

    async def initialize(self) -> None:
        for initializer in self.initializers:
            # Step name in the log makes a failed startup point at the exact step that failed.
            logger.info("startup.step", step=type(initializer).__name__)
            await initializer.initialize()
