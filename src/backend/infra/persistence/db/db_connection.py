"""SQLAlchemy async engine + session management for one configured database."""
from asyncio import current_task
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import URL
from sqlalchemy.ext import asyncio as sqlalchemy_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_scoped_session, async_sessionmaker

from backend.domain.settings.providers import DBSettings


def database_url(settings: DBSettings) -> URL:
    """Build the connection URL for `settings`.

    URL.create escapes special characters, so a password containing '@', '/' or ':' still
    works (string formatting would produce a broken URL). Shared with the migration runner so
    the app and migrations always connect to exactly the same database.
    """
    return URL.create(
        drivername=settings.driver,
        username=settings.user.get_secret_value(),
        password=settings.password.get_secret_value(),
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


class DatabaseConnection:
    def __init__(self, settings: DBSettings):
        self.settings = settings

        # Step 1: the connection pool. Called through the module on purpose: OpenTelemetry's
        # SQLAlchemy instrumentation replaces `sqlalchemy.ext.asyncio.create_async_engine` at
        # startup, and a name imported at the top of this file would still point to the
        # original, so SQL would go untraced.
        self.engine = sqlalchemy_asyncio.create_async_engine(
            database_url(settings),
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            # Test each pooled connection before use, so a Postgres restart doesn't surface
            # as errors on the first requests afterwards.
            pool_pre_ping=True,
        )

        # Step 2: session factory. expire_on_commit=False lets returned objects be read after
        # the transaction ends without triggering lazy reloads.
        self._session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            autoflush=False,
            expire_on_commit=False,
        )

        # Step 3: one session per asyncio task, so concurrent requests never share a transaction.
        self.SessionFactory = async_scoped_session(self._session_factory, scopefunc=current_task)

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        """Unit of work: commit if the block succeeds, roll back and re-raise if it fails."""
        session = self.SessionFactory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
            await self.SessionFactory.remove()

    async def dispose(self) -> None:
        """Close all pooled connections (process shutdown)."""
        await self.engine.dispose()
