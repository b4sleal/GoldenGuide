"""Application database unit of work: one session, the app repositories bound to it.

Pass `session` to join an existing transaction (PrimaryUnitOfWork); otherwise a new one is opened
and committed (or rolled back) when the block ends.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio.session import AsyncSession

from backend.infra.persistence.db.db_connection import DatabaseConnection
from backend.domain.ports.repositories.app.app_db import AppRepositories
from backend.core.factories.registry import APP_REPO_REGISTRY

class SQLAppDB:
    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.engine = db.engine

        try:
            self._repo_factory = APP_REPO_REGISTRY[db.settings.provider]
        except KeyError:
            raise ValueError(
                f"No app repository implementation registered for "
                f"{db.settings.provider!r}"
            ) from None

    @asynccontextmanager
    async def start(
            self,
            session: AsyncSession | None = None,
    ) -> AsyncIterator[AppRepositories]:
        if session is not None:
            repos = self._repo_factory(session)
            yield AppRepositories(**repos)
            return

        async with self.db.session_scope() as owned_session:
            repos = self._repo_factory(owned_session)
            yield AppRepositories(**repos)