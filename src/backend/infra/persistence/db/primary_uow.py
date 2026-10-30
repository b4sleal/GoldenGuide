"""Unit of work spanning app and school repositories in one session (valid while both share a database)."""
from contextlib import AsyncExitStack, asynccontextmanager

from backend.domain.ports.repositories.primary_uow import PrimaryUOWRepositories
from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.ports.repositories.school.school_db import SchoolDB
from backend.infra.persistence.db.db_connection import DatabaseConnection

class PrimaryUnitOfWork:
    def __init__(
            self,
            db: DatabaseConnection,
            app_db: AppDB,
            school_db: SchoolDB,
    ):
        self.db = db
        self.app_db = app_db
        self.school_db = school_db

    @asynccontextmanager
    async def start(self):
        async with self.db.session_scope() as session:
            async with AsyncExitStack() as stack:
                app = await stack.enter_async_context(
                    self.app_db.start(session=session)
                )
                school = await stack.enter_async_context(
                    self.school_db.start(session=session)
                )

                yield PrimaryUOWRepositories(app=app, school=school)