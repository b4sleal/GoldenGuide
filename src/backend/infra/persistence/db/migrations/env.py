"""Alembic environment: how migrations connect, and which models they compare against.

Alembic executes this file for every command (upgrade, revision --autogenerate, check, ...).

Connection URL, in order:
    1. config.attributes["database_url"], set by runner.py (provision job, tests)
    2. otherwise the active database from GoldenGuide's normal config (CLI use by developers)
"""
import asyncio
import logging

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.ext.asyncio import create_async_engine

from backend.infra.persistence.db.app.app_tables import AppBaseTable
from backend.infra.persistence.db.migrations.runner import migration_database_url
from backend.infra.persistence.db.school.school_tables import SchoolBaseTable

config = context.config

# Every table GoldenGuide owns. Autogenerate diffs the database against these models.
target_metadata = [AppBaseTable.metadata, SchoolBaseTable.metadata]

# Arbitrary constant identifying "GoldenGuide migrations" for pg_advisory_xact_lock.
# Two migration runners at once (e.g. two deploys) serialize on it instead of racing on DDL.
_MIGRATION_LOCK_ID = 7_310_250_001


def _database_url() -> URL:
    """Resolve the target database (see module docstring for precedence)."""
    url = config.attributes.get("database_url")
    if url is not None:
        return url

    # CLI path: load the same configuration the app uses. Imported here so programmatic callers,
    # which always pass a URL, never need the full config tree.
    from goldenguide_common.config.env_reader import EnvSecretReader
    from goldenguide_common.config.loader import ConfigLoader

    # The CLI has no structured logging configured; make Alembic's progress lines visible.
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    app_config = ConfigLoader(EnvSecretReader()).load_app_config()
    return migration_database_url(dict(app_config.catalog.active.db))


# Procrastinate's job-queue tables (migration 0005) are created from its own SQL, not from our models.
_EXTERNAL_TABLE_PREFIX = "procrastinate_"


def _include_name(name: str | None, type_: str, parent_names: object) -> bool:
    """Leave tables we do not model out of autogenerate/check, so they are not reported as removed."""
    return not (type_ == "table" and name is not None and name.startswith(_EXTERNAL_TABLE_PREFIX))


def _configure_context(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        # Detect column type changes too (e.g. String(64) -> String(128)), not just added/removed columns.
        compare_type=True,
        include_name=_include_name,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: print the SQL instead of running it.

    Lets a WLU DBA review or apply the exact DDL by hand when direct access is not allowed.
    """
    _configure_context(url=_database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    """Run inside one transaction while holding the migration lock (Postgres DDL is transactional,
    so a failed migration rolls back completely instead of leaving a half-changed schema)."""
    _configure_context(connection=connection)
    with context.begin_transaction():
        # Released automatically when the transaction ends.
        connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _MIGRATION_LOCK_ID})
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect with the app's async driver (asyncpg) and run the migrations synchronously inside it."""
    # NullPool: a one-shot command should not keep idle connections open.
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
