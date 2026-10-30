"""Database fixtures for integration tests.

Point GOLDENGUIDE_TEST_DATABASE_URL at a disposable database. The Compose stack creates one
(`goldenguide_test`, see docker/postgres/bootstrap.sql):

    GOLDENGUIDE_TEST_DATABASE_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/goldenguide_test

Tests may drop and recreate every table in it. Never point this at a database with real data.
"""
import pytest
from sqlalchemy.engine import URL, make_url

from backend.infra.persistence.db.migrations.runner import upgrade_to_head


@pytest.fixture(scope="session")
def test_database_url(infra_service_url) -> URL:
    raw = infra_service_url("GOLDENGUIDE_TEST_DATABASE_URL")
    url = make_url(raw)
    if url.drivername != "postgresql+asyncpg":
        pytest.fail("Test database must use postgresql+asyncpg")
    # Guard against pointing tests at the development or production database by mistake.
    if not (url.database or "").endswith("_test"):
        pytest.fail(f"Refusing to run against '{url.database}': test database names must end in '_test'")
    return url


@pytest.fixture(scope="session")
def migrated_database_url(test_database_url: URL) -> URL:
    """The test database brought to the latest migration once per test session, exactly as
    production is (no create_all), so tests see the real schema."""
    upgrade_to_head(test_database_url)
    return test_database_url
