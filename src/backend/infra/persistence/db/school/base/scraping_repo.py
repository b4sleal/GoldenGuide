"""SQL scrape-page repository. Its upsert encodes the page lifecycle: retry counts, last error,
and needs_persistence when a successful fetch brings new content.
"""
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy import func, select, union_all, case, ColumnElement, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.base import ReadOnlyColumnCollection

from backend.infra.persistence.db.utils.generic.update_rules import preserve_on_null
from backend.domain.entities.scraping import ScrapePageBase, ScrapePageCreate, ScrapePageField, ScrapePageUpdate, \
    ScrapePageRead, ScrapeStatus
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.query_types import ScrapePageParams
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.school.filters import ScrapePageFilterTranslator
from backend.infra.persistence.db.school.school_tables import (
    SchoolScrapePageTable, Course, WluPage,
)
from backend.infra.persistence.db.utils.generic.db_ops import generic_fetch, generic_update
from backend.infra.persistence.db.utils.generic.upsert_mapping import (
    column_name,
    mapped_table,
    prepare_rows,
    update_columns,
)
from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting

logger = structlog.get_logger()


class SqlScrapingRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps):
        self.session = session
        self.dialect = dialect

        # Domain field names whose column is named differently.
        self.aliases: dict[str, InstrumentedAttribute] = {
            ScrapePageField.ERROR.value: SchoolScrapePageTable.last_error,
            ScrapePageField.ATTEMPTED_AT.value: SchoolScrapePageTable.last_attempted_at,
            ScrapePageField.CREATED_AT.value: SchoolScrapePageTable.first_seen_at,
        }

    async def upsert_scrape_page(
            self,
            payload: ScrapePageCreate,
    ) -> PrimaryKey:
        ids = await self.upsert_scrape_pages([payload])
        return ids[0]

    async def upsert_scrape_pages(self, payloads: list[ScrapePageCreate]) -> list[PrimaryKey]:
        """Insert or update pages; the lifecycle columns follow _build_lifecycle_updates."""
        identity = ScrapePageBase.IDENTITY_FIELDS
        columns = update_columns(ScrapePageUpdate, identity_fields=identity, aliases=self.aliases)

        return await self.dialect.upsert(
            self.session,
            table=mapped_table(SchoolScrapePageTable),
            rows=prepare_rows(payloads, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
            build_updates=lambda existing, incoming: self._build_lifecycle_updates(existing, incoming, columns),
        )

    async def fetch_pages[T: BaseModel = ScrapePageRead](
            self,
            page_params: ScrapePageParams,
            filters: ScrapePageFilter | None = None,
            *,
            view_model: type[T] = ScrapePageRead
    ) -> list[T]:
        stmt = select(SchoolScrapePageTable)

        mapped_urls = self._mapped_urls_subquery() if filters and filters.is_unmapped else None
        stmt = ScrapePageFilterTranslator.apply(stmt, filters, mapped_urls)

        stmt = apply_sorting(
            stmt=stmt,
            model=SchoolScrapePageTable,
            order_by=page_params.order_by,
            aliases=self.aliases,
            stable_tiebreaker=ScrapePageField.ID.value,
        )

        return await generic_fetch(
            session=self.session,
            stmt=stmt,
            db_model=SchoolScrapePageTable,
            view_model=view_model,
            page_params=page_params,
            aliases=self.aliases,
        )

    async def update_scrape_pages(
            self,
            page_ids: list[int],
            update_data: ScrapePageUpdate,
    ) -> None:
        if not page_ids:
            return

        stmt = update(SchoolScrapePageTable).where(
            SchoolScrapePageTable.id.in_(page_ids)
        )

        await generic_update(
            self.session,
            stmt,
            update_data,
            self.aliases,
        )

    async def count_pages(self, filters: ScrapePageFilter | None = None) -> int:
        stmt = select(func.count()).select_from(SchoolScrapePageTable)

        mapped_urls = self._mapped_urls_subquery() if filters and filters.is_unmapped else None
        stmt = ScrapePageFilterTranslator.apply(stmt, filters, mapped_urls)

        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_pages_by(
            self,
            field: ScrapePageField,
            filters: ScrapePageFilter | None = None,
    ) -> dict[str, int]:
        # Domain field -> column (through aliases when the names differ).
        column = self.aliases.get(field.value) or getattr(SchoolScrapePageTable, field.value)

        stmt = select(column, func.count()).select_from(SchoolScrapePageTable)
        mapped_urls = self._mapped_urls_subquery() if filters and filters.is_unmapped else None

        stmt = ScrapePageFilterTranslator.apply(stmt, filters, mapped_urls)
        stmt = stmt.group_by(column)

        result = await self.session.execute(stmt)

        return {str(value): int(count) for value, count in result.all()}

    @staticmethod
    def _mapped_urls_subquery():
        # URLs that already produced a course or page row (for "unmapped page" audits).
        course_urls = select(Course.calendar_url.label("url")).where(Course.calendar_url.is_not(None))
        academic_urls = select(WluPage.url.label("url")).where(WluPage.url.is_not(None))

        return union_all(course_urls, academic_urls).subquery()

    def _build_lifecycle_updates(
            self,
            existing: ReadOnlyColumnCollection,
            incoming: ReadOnlyColumnCollection,
            columns: tuple[str, ...]
    ) -> dict[str, ColumnElement[Any]]:
        """
        Pure SQLAlchemy logic defining the scraping state machine.
        Dialect-agnostic: Reusable by Postgres, MySQL, or any future adapter.
        """
        failures = (ScrapeStatus.RETRYABLE_ERROR.value, ScrapeStatus.PERMANENT_ERROR.value)
        success = ScrapeStatus.SUCCESS.value

        updates = preserve_on_null(existing, incoming, columns)

        updates["retry_count"] = case(
            (incoming.status.in_(failures), existing.retry_count + 1),
            (incoming.status == success, 0),
            else_=existing.retry_count,
        )
        updates["last_error"] = case(
            (incoming.status == success, None),
            else_=updates["last_error"],
        )
        updates["needs_persistence"] = case(
            (
                (incoming.status == ScrapeStatus.SUCCESS.value)
                & incoming.content_hash.is_distinct_from(existing.content_hash),
                True,
            ),
            else_=existing.needs_persistence,
        )

        return updates