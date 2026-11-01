"""Migrations are the only way the schema changes, so they must stay correct and in sync with the models."""
import asyncio
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import text
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


def test_answer_content_migration_preserves_legacy_history(migrated_database_url):
    conversation_id = uuid4()
    config = alembic_config(migrated_database_url)

    async def seed():
        engine = create_async_engine(migrated_database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(
                    "INSERT INTO conversations (id, client_id_hash) VALUES (:id, 'legacy-device')"
                ), {"id": conversation_id})
                await connection.execute(text(
                    "INSERT INTO chat_messages (conversation_id, position, role, content, status) "
                    "VALUES (:id, 1, 'assistant', 'Original saved answer', 'complete')"
                ), {"id": conversation_id})
        finally:
            await engine.dispose()

    async def verify_and_clean():
        engine = create_async_engine(migrated_database_url)
        try:
            async with engine.begin() as connection:
                row = (await connection.execute(text(
                    "SELECT content, status, answer_content FROM chat_messages WHERE conversation_id = :id"
                ), {"id": conversation_id})).mappings().one()
                assert dict(row) == {"content": "Original saved answer", "status": "complete", "answer_content": None}
        finally:
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conversation_id})
            await engine.dispose()

    # This uses the guarded disposable _test database, never application history.
    command.downgrade(config, "0003")
    try:
        asyncio.run(seed())
    finally:
        upgrade_to_head(migrated_database_url)
    asyncio.run(verify_and_clean())


async def test_startup_check_rejects_an_outdated_schema(migrated_database_url):
    # Alembic runs its own event loop, so from async code it must run in a worker thread.
    def downgrade():
        command.downgrade(alembic_config(migrated_database_url), "base")

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
