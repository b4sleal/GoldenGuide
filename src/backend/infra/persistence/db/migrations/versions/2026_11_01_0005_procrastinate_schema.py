"""Create Procrastinate's job-queue schema (version 3.10.0) for worker execution.

Procrastinate ships its schema as plain SQL and has no Alembic integration, so this migration runs a
frozen copy of that SQL (migrations/sql/procrastinate_3_10_0_schema.sql, copied verbatim from the
pinned package). A frozen copy keeps this revision reproducible after the package is upgraded; each
Procrastinate upgrade gets its own revision running that release's migration scripts
(docs/backend/operations.md#upgrade-procrastinate-the-job-queue).

Its objects are all prefixed `procrastinate_` (4 tables, 3 types, functions, triggers) and are not
SQLAlchemy models; env.py excludes them from autogenerate/check.

Revision ID: 0005
Revises: 0004
"""
from collections.abc import Sequence
from pathlib import Path

from alembic import context, op
from sqlalchemy.util import await_only

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA_SQL = Path(__file__).resolve().parents[1] / "sql" / "procrastinate_3_10_0_schema.sql"

# Objects created by the schema above, dropped in dependency order on downgrade.
TABLES = ("procrastinate_events", "procrastinate_periodic_defers", "procrastinate_jobs", "procrastinate_workers")
TYPES = ("procrastinate_job_to_defer_v1", "procrastinate_job_event_type", "procrastinate_job_status")


def _execute_script(sql: str) -> None:
    """Run a multi-statement script on the raw asyncpg connection.

    SQLAlchemy's asyncpg driver prepares each statement, and a prepared statement cannot hold several
    commands; asyncpg's `execute` without arguments uses the simple query protocol, which can. It
    runs inside Alembic's transaction (env.py), so a failure still rolls everything back.
    Offline mode (`alembic upgrade --sql`, for DBA review) has no connection: the script is printed.
    """
    if context.is_offline_mode():
        op.execute(sql)
        return
    driver_connection = op.get_bind().connection.driver_connection
    if driver_connection is None:
        raise RuntimeError("Migration 0005 needs a live database connection")
    await_only(driver_connection.execute(sql))


def upgrade() -> None:
    _execute_script(SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    # Functions first (triggers depend on them through the tables, dropped with CASCADE below).
    _execute_script(
        """
        DO $$
        DECLARE fn regprocedure;
        BEGIN
            FOR fn IN SELECT p.oid::regprocedure FROM pg_proc p
                      JOIN pg_namespace n ON n.oid = p.pronamespace
                      WHERE p.proname LIKE 'procrastinate\\_%' AND n.nspname = current_schema()
            LOOP
                EXECUTE 'DROP FUNCTION ' || fn || ' CASCADE';
            END LOOP;
        END;
        $$;
        """
    )
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for type_name in TYPES:
        op.execute(f"DROP TYPE IF EXISTS {type_name} CASCADE")
