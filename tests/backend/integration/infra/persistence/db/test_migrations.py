"""Migrations are the only way the schema changes, so they must stay correct and in sync with the models."""
import asyncio

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine

from backend.infra.persistence.db.migrations.runner import (
    SchemaVersionError,
    alembic_config,
    assert_schema_current,
    check_models_match,
    upgrade_to_head,
)


def test_models_have_no_unmigrated_changes(migrated_database_url):
    # Fails when a model changed without a migration. Fix: `uv run alembic revision --autogenerate -m "..."`.
    check_models_match(migrated_database_url)


def test_full_downgrade_and_upgrade_round_trip(migrated_database_url):
    # Every migration's downgrade() must work, or rolling back a bad deploy is impossible.
    config = alembic_config(migrated_database_url)
    command.downgrade(config, "base")
    upgrade_to_head(migrated_database_url)
    check_models_match(migrated_database_url)


async def test_startup_check_rejects_an_outdated_schema(migrated_database_url):
    # Alembic runs its own event loop, so from async code it must run in a worker thread.
    downgrade = lambda: command.downgrade(alembic_config(migrated_database_url), "base")  # noqa: E731

    engine = create_async_engine(migrated_database_url)
    try:
        await assert_schema_current(engine)  # at head: passes

        await engine.dispose()
        await asyncio.to_thread(downgrade)
        with pytest.raises(SchemaVersionError, match="Run the provision job"):
            await assert_schema_current(engine)
    finally:
        await engine.dispose()
        # Leave the database migrated for other tests.
        await asyncio.to_thread(upgrade_to_head, migrated_database_url)
