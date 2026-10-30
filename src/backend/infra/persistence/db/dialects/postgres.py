"""PostgreSQL SqlDialectOps: INSERT ... ON CONFLICT ... RETURNING, chunked under asyncpg's bind limit."""
from collections.abc import Iterator, Mapping, Sequence
from hashlib import sha256
from itertools import batched
from typing import Any

from sqlalchemy import Table, func, select
from sqlalchemy.dialects.postgresql import Insert, insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.dialects.ops import UpdateBuilder, UpdateCondition

# asyncpg hard limit is 32767. We use 32000 to leave breathing room for explicit SET parameters.
MAX_BIND_PARAMS = 32000


class PostgresDialectOps:
    """SqlDialectOps for PostgreSQL: INSERT ... ON CONFLICT ... RETURNING, chunked for asyncpg."""

    async def lock_transaction(self, session: AsyncSession, resource: str) -> None:
        # Stable across processes; collisions only serialize unrelated submissions.
        key = int.from_bytes(sha256(resource.encode()).digest()[:8], signed=True)
        await session.execute(select(func.pg_advisory_xact_lock(key)))

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
        returned: list[PrimaryKey] = []

        for stmt in _insert_batches(table, rows):
            updates = dict(build_updates(table.c, stmt.excluded))
            if not updates:
                raise ValueError("Upsert requires at least one update assignment.")

            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c[name] for name in conflict_columns],
                set_=updates,
                where=update_where(table.c, stmt.excluded) if update_where else None,
            )
            returned.extend(await _execute_returning(session, table, stmt))

        return returned

    async def insert_ignore(
            self,
            session: AsyncSession,
            *,
            table: Table,
            rows: Sequence[Mapping[str, Any]],
            conflict_columns: Sequence[str],
    ) -> list[PrimaryKey]:
        returned: list[PrimaryKey] = []

        for stmt in _insert_batches(table, rows):
            stmt = stmt.on_conflict_do_nothing(
                index_elements=[table.c[name] for name in conflict_columns],
            )
            returned.extend(await _execute_returning(session, table, stmt))

        return returned


def _insert_batches(table: Table, rows: Sequence[Mapping[str, Any]]) -> Iterator[Insert]:
    """One INSERT per chunk, sized so a full-width row batch stays under the driver's bind limit."""
    if not table.primary_key.columns:
        raise ValueError(f"{table.name} requires a primary key.")

    batch_size = max(1, MAX_BIND_PARAMS // len(table.c))
    for batch in batched(rows, batch_size):
        yield insert(table).values(list(batch))


async def _execute_returning(session: AsyncSession, table: Table, stmt: Insert) -> list[PrimaryKey]:
    primary_keys = list(table.primary_key.columns)
    result = await session.execute(stmt.returning(*primary_keys))

    if len(primary_keys) == 1:
        return list(result.scalars().all())
    return [tuple(row) for row in result.all()]
