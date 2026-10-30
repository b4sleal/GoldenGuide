"""Provision job: bring every data store to the state this code version expects, then exit.

    uv run python -m backend.core.startup.provision        # locally
    docker compose run --rm provision                      # in Docker (also runs automatically)

Runs once per deploy, BEFORE the API starts (docker-compose: `service_completed_successfully`;
AWS ECS: a one-off task in the deploy pipeline). Every step is idempotent, so re-running is safe:
    1. PostgreSQL: apply pending Alembic migrations
    2. Object storage: create missing buckets
    3. Vector store: create missing collections, verify existing ones match their configured version

It does NOT create the database itself. That is infrastructure provisioning: docker/postgres/
bootstrap.sql locally, Terraform/CDK (or the DBA) for RDS in production.

Exit code 0 = everything is ready; non-zero = deploy must stop (the API would refuse to start anyway).
"""
import asyncio
import sys

import structlog

from backend.core.startup.runtime import build_container
from backend.infra.persistence.db.migrations.runner import migration_database_url, upgrade_to_head
from goldenguide_common.logging.telemetry import shutdown_telemetry

logger = structlog.get_logger("backend.provision")


def main() -> int:
    # Same bootstrap as the API: structured logging, tracing, configuration, DI container.
    container = build_container()
    try:
        # Step 1: database schema. Runs outside asyncio because Alembic's env.py starts its own loop.
        logger.info("provision.migrations_started")
        upgrade_to_head(migration_database_url(dict(container.app_config().catalog.active.db)))
        logger.info("provision.migrations_complete")

        # Step 2-3: buckets and collections (async adapters).
        asyncio.run(container.provisioning_runner().initialize())

        logger.info("provision.complete")
        return 0
    except Exception:
        # Logged once with the full traceback, then a non-zero exit stops the deploy.
        logger.exception("provision.failed")
        return 1
    finally:
        shutdown_telemetry()


if __name__ == "__main__":
    sys.exit(main())
