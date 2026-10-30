"""API startup step: refuse to serve traffic against a database schema this code doesn't expect."""
import structlog

from backend.infra.persistence.db.db_connection import DatabaseConnection
from backend.infra.persistence.db.migrations.runner import assert_schema_current

logger = structlog.get_logger(__name__)


class SchemaVersionCheck:
    """Read-only check that the database is at the latest migration.

    Migrations are applied by the provision job, never by API replicas. If a deploy skipped that
    job, the API fails at startup with a clear message instead of failing on the first query
    that touches a missing column.
    """

    def __init__(self, db: DatabaseConnection):
        self.db = db

    async def initialize(self) -> None:
        await assert_schema_current(self.db.engine)
        logger.info("startup.schema_current")
