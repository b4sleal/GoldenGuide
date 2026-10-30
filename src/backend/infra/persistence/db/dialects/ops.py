"""SqlDialectOps: the statements plain SQLAlchemy cannot express portably (upsert, insert-ignore).

Repositories prepare rows and decide update rules; a dialect implements only the statement mechanics.
"""
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Protocol

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import ReadOnlyColumnCollection
from sqlalchemy.sql.elements import ColumnElement

from backend.domain.ports.repositories.types import PrimaryKey

# (existing row columns, incoming row columns) -> SET assignments for a conflicting row.
UpdateBuilder = Callable[
    [ReadOnlyColumnCollection, ReadOnlyColumnCollection],
    Mapping[str, ColumnElement[Any]],
]

UpdateCondition = Callable[
    [ReadOnlyColumnCollection, ReadOnlyColumnCollection],
    ColumnElement[bool],
]


class SqlDialectOps(Protocol):
    """
    The SQL statements generic SQLAlchemy cannot express portably.

    Repositories own all entity logic and hand fully prepared rows to these
    operations; each dialect implements only the statement mechanics
    (conflict handling, returning keys, driver parameter limits).

    Anything plain SQLAlchemy cannot express portably (or cleanly) belongs here as a new method.
    """

    async def lock_transaction(self, session: AsyncSession, resource: str) -> None:
        """Hold an exclusive named lock until commit or rollback."""
        ...

    async def upsert(
            self,
            session: AsyncSession,
            *,
            table: Table,
            rows: Sequence[Mapping[str, Any]],
            conflict_columns: Sequence[str],
            build_updates: UpdateBuilder,
            update_where: UpdateCondition | None = None,
    ) -> list[PrimaryKey]:
        """Insert rows, updating conflicting ones; returns the primary key of every affected row."""
        ...

    async def insert_ignore(
            self,
            session: AsyncSession,
            *,
            table: Table,
            rows: Sequence[Mapping[str, Any]],
            conflict_columns: Sequence[str],
    ) -> list[PrimaryKey]:
        """Insert rows, skipping conflicting ones; returns primary keys of the newly inserted rows only."""
        ...
