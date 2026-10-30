"""Programmatic access to GoldenGuide's Alembic migrations.

Three callers, three operations:
    provision job (core/startup/provision.py)  upgrade_to_head()     apply pending migrations
    API startup   (SchemaVersionCheck)         assert_schema_current()  refuse to serve an old schema
    tests                                      check_models_match()  models and migrations must agree

Developers use the Alembic CLI for authoring (alembic.ini at the repo root), e.g.
    uv run alembic revision --autogenerate -m "add feedback table"
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine

from backend.domain.settings.providers import DBSettings
from backend.infra.persistence.db.db_connection import database_url

# This package holds env.py and versions/, so the location works regardless of the working directory.
MIGRATIONS_DIR = Path(__file__).resolve().parent


class SchemaVersionError(RuntimeError):
    """The database schema is not at the version this code expects."""


def migration_database_url(databases: dict[str, DBSettings]) -> URL:
    """The single database that migrations target.

    The `app` and `school` tables currently live in one Postgres database and share one migration
    history. If the config ever points them at different databases, a single history would migrate
    only one of them, so fail loudly instead of half-migrating.
    """
    urls = {name: database_url(settings) for name, settings in databases.items()}
    distinct = {url.render_as_string(hide_password=False) for url in urls.values()}
    if len(distinct) != 1:
        raise SchemaVersionError(
            "Active databases differ "
            f"({', '.join(f'{n}={u.database}' for n, u in urls.items())}); "
            "separate databases need separate migration histories."
        )
    return next(iter(urls.values()))


def alembic_config(url: URL) -> Config:
    """Alembic Config built in code. The URL travels in `attributes`, never in an .ini file,
    so passwords are not written anywhere and '%' in a password cannot break ini interpolation."""
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Same naming as alembic.ini, so files read chronologically however they were created.
    config.set_main_option("file_template", "%%(year)d_%%(month).2d_%%(day).2d_%%(rev)s_%%(slug)s")
    config.attributes["database_url"] = url
    return config


def upgrade_to_head(url: URL) -> None:
    """Apply every pending migration. Safe to run repeatedly and from concurrent jobs:
    env.py holds a Postgres advisory lock, so a second runner waits, then finds nothing to do.

    Must be called outside a running event loop (env.py runs its own asyncio loop).
    """
    command.upgrade(alembic_config(url), "head")


def check_models_match(url: URL) -> None:
    """Raise if the SQLAlchemy models contain changes no migration covers (alembic check).

    Run against a fully migrated database. It catches "added a column to the model but forgot
    the migration" before deployment.
    """
    command.check(alembic_config(url))


def expected_heads() -> set[str]:
    """Latest revision id(s) in versions/: the schema version this code expects."""
    return set(ScriptDirectory.from_config(alembic_config(URL.create("postgresql"))).get_heads())


async def assert_schema_current(engine: AsyncEngine) -> None:
    """Fail startup unless the database is at exactly the revision this code expects.

    Read-only: the API never migrates, so N replicas starting together cannot race on DDL.
    """
    # Read the revision Alembic recorded in the database (the alembic_version table).
    async with engine.connect() as connection:
        current = await connection.run_sync(
            lambda sync_connection: set(MigrationContext.configure(sync_connection).get_current_heads())
        )

    expected = expected_heads()
    if current != expected:
        raise SchemaVersionError(
            f"Database schema is at {sorted(current) or 'no version (empty database)'}, "
            f"code expects {sorted(expected)}. Run the provision job: "
            "`docker compose run --rm provision` (or `uv run python -m backend.core.startup.provision`)."
        )
