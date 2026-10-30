"""SQL settings repository: append-only versions per key; the newest row is current."""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.persistence.db.app.app_tables import AppSettingsTable

logger = structlog.get_logger()


class SqlSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> str | None:
        """Fetches the MOST RECENT raw JSON string from the database."""
        stmt = (
            select(AppSettingsTable)
            .where(AppSettingsTable.key == key)
            .order_by(AppSettingsTable.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return row.value if row else None

    async def save(self, key: str, value: str) -> None:
        """Appends a new version of the settings as a brand new row."""
        obj = AppSettingsTable(
            key=key,
            value=value,
        )
        self.session.add(obj)
        await self.session.flush()

        logger.debug("settings_version_appended_to_db", key=key)