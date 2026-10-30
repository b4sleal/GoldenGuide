"""School database unit of work: one session, the school repositories bound to it (see SQLAppDB)."""
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio.session import AsyncSession

from backend.core.factories.registry import SCHOOL_REPO_REGISTRY

from backend.domain.ports.repositories.school.school_db import SchoolRepositories
from backend.infra.persistence.db.db_connection import DatabaseConnection

class SQLSchoolDB:
    def __init__(self, db: DatabaseConnection):
        self.db = db
        self.engine = db.engine

        try:
            self._repo_factory = SCHOOL_REPO_REGISTRY[db.settings.provider]
        except KeyError:
            raise ValueError(
                f"No school repository implementation registered for "
                f"{db.settings.provider!r}"
            ) from None

    @asynccontextmanager
    async def start(
            self,
            session: AsyncSession | None = None,
    ) -> AsyncIterator[SchoolRepositories]:

        if session is not None:
            repos = self._repo_factory(session)
            yield SchoolRepositories(**repos)
            return

        async with self.db.session_scope() as owned_session:
            repos = self._repo_factory(owned_session)
            yield SchoolRepositories(**repos)