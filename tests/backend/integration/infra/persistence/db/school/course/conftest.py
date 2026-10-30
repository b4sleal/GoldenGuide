"""Course-term fixtures on the real migrated schema. Each test runs in a transaction that is rolled back."""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps
from backend.infra.persistence.db.school.base.course_term_repo import SqlCourseTermRepository


@pytest.fixture
async def session(migrated_database_url):
    engine = create_async_engine(migrated_database_url.render_as_string(hide_password=False))
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            # Repository flushes/commits become savepoints inside the outer transaction.
            async with AsyncSession(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield session
            await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
def course_terms(session) -> SqlCourseTermRepository:
    return SqlCourseTermRepository(session, PostgresDialectOps())
