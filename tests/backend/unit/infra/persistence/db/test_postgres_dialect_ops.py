"""PostgresDialectOps statement mechanics, verified on compiled SQL without a live database."""
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql

from backend.infra.persistence.db.dialects import postgres
from backend.infra.persistence.db.dialects.postgres import PostgresDialectOps

METADATA = MetaData()
ITEMS = Table(
    "items", METADATA,
    Column("id", Integer, primary_key=True),
    Column("code", String),
    Column("name", String),
)
NO_PRIMARY_KEY = Table("loose", METADATA, Column("code", String))
LINKS = Table(
    "links", METADATA,
    Column("left_id", Integer, primary_key=True),
    Column("right_id", Integer, primary_key=True),
)


class Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class RecordingSession:
    """Captures executed statements and answers each with the next queued RETURNING result."""

    def __init__(self, *returned_batches):
        self.statements = []
        self._returned = list(returned_batches)

    async def execute(self, stmt):
        self.statements.append(stmt)
        return Result(self._returned.pop(0))

    def sql(self, index=0) -> str:
        return str(self.statements[index].compile(dialect=postgresql.dialect()))


def rows(count):
    return [{"id": None, "code": f"c{i}", "name": f"n{i}"} for i in range(count)]


def overwrite_name(existing, incoming):
    return {"name": incoming.name}


async def test_upsert_updates_conflicting_rows_and_returns_primary_keys():
    session = RecordingSession([1, 2])

    ids = await PostgresDialectOps().upsert(
        session, table=ITEMS, rows=rows(2), conflict_columns=["code"], build_updates=overwrite_name,
    )

    assert ids == [1, 2]
    sql = session.sql()
    assert "ON CONFLICT (code) DO UPDATE SET name = excluded.name" in sql
    assert sql.endswith("RETURNING items.id")


async def test_upsert_applies_the_optional_update_condition():
    session = RecordingSession([1])

    await PostgresDialectOps().upsert(
        session, table=ITEMS, rows=rows(1), conflict_columns=["code"], build_updates=overwrite_name,
        update_where=lambda existing, incoming: existing.name != incoming.name,
    )

    assert "WHERE items.name != excluded.name" in session.sql()


async def test_upsert_chunks_batches_under_the_bind_parameter_limit(monkeypatch):
    # 3 columns per row and a 6-parameter budget -> 2 rows per statement.
    monkeypatch.setattr(postgres, "MAX_BIND_PARAMS", 6)
    session = RecordingSession([1, 2], [3, 4], [5])

    ids = await PostgresDialectOps().upsert(
        session, table=ITEMS, rows=rows(5), conflict_columns=["code"], build_updates=overwrite_name,
    )

    assert len(session.statements) == 3
    assert ids == [1, 2, 3, 4, 5]


async def test_upsert_of_no_rows_executes_nothing():
    session = RecordingSession()

    ids = await PostgresDialectOps().upsert(
        session, table=ITEMS, rows=[], conflict_columns=["code"], build_updates=overwrite_name,
    )

    assert ids == []
    assert session.statements == []


async def test_upsert_rejects_an_empty_update_assignment():
    with pytest.raises(ValueError, match="at least one update"):
        await PostgresDialectOps().upsert(
            RecordingSession(), table=ITEMS, rows=rows(1), conflict_columns=["code"],
            build_updates=lambda existing, incoming: {},
        )


async def test_insert_ignore_skips_conflicts_and_returns_only_inserted_keys():
    session = RecordingSession([7])

    ids = await PostgresDialectOps().insert_ignore(
        session, table=ITEMS, rows=rows(2), conflict_columns=["code"],
    )

    assert ids == [7]
    sql = session.sql()
    assert "ON CONFLICT (code) DO NOTHING" in sql
    assert sql.endswith("RETURNING items.id")


async def test_insert_ignore_chunks_batches_under_the_bind_parameter_limit(monkeypatch):
    monkeypatch.setattr(postgres, "MAX_BIND_PARAMS", 6)
    session = RecordingSession([1, 2], [3])

    ids = await PostgresDialectOps().insert_ignore(
        session, table=ITEMS, rows=rows(3), conflict_columns=["code"],
    )

    assert len(session.statements) == 2
    assert ids == [1, 2, 3]


async def test_composite_primary_keys_are_returned_as_tuples():
    session = RecordingSession([(1, 2)])

    ids = await PostgresDialectOps().insert_ignore(
        session, table=LINKS, rows=[{"left_id": 1, "right_id": 2}], conflict_columns=["left_id", "right_id"],
    )

    assert ids == [(1, 2)]


async def test_tables_without_a_primary_key_are_rejected():
    with pytest.raises(ValueError, match="requires a primary key"):
        await PostgresDialectOps().insert_ignore(
            RecordingSession(), table=NO_PRIMARY_KEY, rows=[{"code": "x"}], conflict_columns=["code"],
        )
