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


CALENDAR = "https://academic-calendar.wlu.ca"
# url -> level migration 0006 must set: only calendar URLs with a known `cal` get one.
LEVEL_PAGES = {
    f"{CALENDAR}/department.php?cal=1&d=1&s=1&y=93": "undergraduate",
    f"{CALENDAR}/program.php?cal=3&d=1&p=1&s=1&y=94": "graduate",
    f"{CALENDAR}/department.php?cal=10&d=1&s=1&y=93": None,  # Not cal=1.
    f"{CALENDAR}/department.php?cal=2&d=1&s=1&y=76": None,   # Unknown calendar.
}
WEBSITE_PAGE = "https://students.wlu.ca/tuition?cal=1"     # Not the calendar: stays NULL.
GRADUATE_COURSE_URL = f"{CALENDAR}/course.php?c=1&cal=3&d=1&s=1&y=94"


def test_academic_level_migration_fills_only_calendar_rows_and_downgrades(migrated_database_url):
    config = alembic_config(migrated_database_url)

    async def run(statements: list[tuple[str, dict]]):
        engine = create_async_engine(migrated_database_url)
        try:
            async with engine.begin() as connection:
                for statement, params in statements:
                    await connection.execute(text(statement), params)
        finally:
            await engine.dispose()

    page = (
        "INSERT INTO wlu_pages (url, version, site_name, record_type, title, content, metadata_json) "
        "VALUES (:url, '2026/2027', :site, 'department', 't', 'c', '{}')"
    )
    seed = [(page, {"url": url, "site": "academic_calendar_wlu"}) for url in LEVEL_PAGES]
    seed.append((page, {"url": WEBSITE_PAGE, "site": "students_wlu"}))
    seed.append((
        "INSERT INTO courses (academic_year, institution, subject, subject_code, course_number, campus, "
        "calendar_url, metadata_json) VALUES ('2026/2027', 'WLU', 'Public Safety', 'SAFE', '600', 'Waterloo', :url, '{}')",
        {"url": GRADUATE_COURSE_URL},
    ))

    page_urls = [*LEVEL_PAGES, WEBSITE_PAGE]

    async def select(statement: str, params: dict | None = None):
        engine = create_async_engine(migrated_database_url)
        try:
            async with engine.connect() as connection:
                return (await connection.execute(text(statement), params or {})).all()
        finally:
            await engine.dispose()

    command.downgrade(config, "0005")
    try:
        asyncio.run(run(seed))
    finally:
        upgrade_to_head(migrated_database_url)
    try:
        urls = {"urls": page_urls}
        pages = asyncio.run(select("SELECT url, academic_level FROM wlu_pages WHERE url = ANY(:urls)", urls))
        courses = asyncio.run(select(
            "SELECT calendar_url, academic_level FROM courses WHERE calendar_url = :url", {"url": GRADUATE_COURSE_URL},
        ))
        assert dict(pages) == {**LEVEL_PAGES, WEBSITE_PAGE: None}
        assert dict(courses) == {GRADUATE_COURSE_URL: "graduate"}

        # Downgrading drops only the derived column; the rows stay.
        command.downgrade(config, "0005")
        assert len(asyncio.run(select("SELECT id FROM wlu_pages WHERE url = ANY(:urls)", urls))) == len(page_urls)
    finally:
        upgrade_to_head(migrated_database_url)
        asyncio.run(run([
            ("DELETE FROM wlu_pages WHERE url = ANY(:urls)", {"urls": page_urls}),
            ("DELETE FROM courses WHERE calendar_url = :url", {"url": GRADUATE_COURSE_URL}),
        ]))


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
