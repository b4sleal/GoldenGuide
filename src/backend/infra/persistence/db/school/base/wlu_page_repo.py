"""SQL WLU page repository. Upsert overwrites and flags re-embedding on content change."""
import structlog
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.entities.wlu.wlu_pages import WluPageBase, WluPageCreate, WluPageField, WluPageUpdate, WluPageRead
from backend.domain.ports.repositories.filters import WluPageFilter
from backend.domain.ports.repositories.school.query_types import WluPageParams
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.school.filters import WluPageFilterTranslator
from backend.infra.persistence.db.school.school_tables import WluPage
from backend.infra.persistence.db.utils.generic.db_ops import generic_update, generic_fetch
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting
from backend.infra.persistence.db.utils.generic.update_rules import overwrite_and_flag_reembed
from backend.infra.persistence.db.utils.generic.upsert_mapping import (
    column_name,
    mapped_table,
    prepare_rows,
    update_columns,
)
from backend.domain.ports.repositories.types import PrimaryKey

logger = structlog.get_logger()


class SqlWluPageRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps):
        self.session = session
        self.dialect = dialect
        self.aliases: dict[str, InstrumentedAttribute] = {}

    async def upsert_wlu_page(self, record: WluPageCreate) -> PrimaryKey:
        ids = await self.upsert_wlu_pages([record], )
        return ids[0]

    async def upsert_wlu_pages(
            self,
            records: list[WluPageCreate],
    ) -> list[PrimaryKey]:
        identity = WluPageBase.IDENTITY_FIELDS
        columns = update_columns(WluPageUpdate, identity_fields=identity, aliases=self.aliases)

        return await self.dialect.upsert(
            self.session,
            table=mapped_table(WluPage),
            rows=prepare_rows(records, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
            build_updates=overwrite_and_flag_reembed(
                columns,
                embed_fields=WluPageBase.EMBED_FIELDS,
                flag_field=WluPageField.NEEDS_EMBEDDING,
                aliases=self.aliases,
            ),
        )

    async def update_wlu_pages(
            self,
            page_ids: list[int],
            update_data: WluPageUpdate,
    ) -> None:
        if not page_ids:
            return

        stmt = update(WluPage).where(WluPage.id.in_(page_ids))
        await generic_update(self.session, stmt, update_data, self.aliases)

    async def fetch_records[T: BaseModel = WluPageRead](
            self,
            page_params: WluPageParams,
            filters: WluPageFilter | None = None,
            *,
            view_model: type[T] = WluPageRead
    ) -> list[T]:
        stmt = select(WluPage)
        stmt = WluPageFilterTranslator.apply(stmt, filters)
        stmt = apply_sorting(
            stmt=stmt,
            model=WluPage,
            order_by=page_params.order_by,
            aliases=self.aliases,
            stable_tiebreaker=WluPageField.ID.value,
        )

        return await generic_fetch(
            session=self.session,
            stmt=stmt,
            db_model=WluPage,
            view_model=view_model,
            page_params=page_params,
            aliases=self.aliases,
        )

    async def count_all_records(self, filters: WluPageFilter | None = None) -> int:
        stmt = select(func.count()).select_from(WluPage)
        stmt = WluPageFilterTranslator.apply(stmt, filters)

        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_by_record_type(self, filters: WluPageFilter | None = None) -> dict[str, int]:
        record_type_column = WluPage.record_type
        stmt = select(record_type_column, func.count())
        stmt = WluPageFilterTranslator.apply(stmt, filters)
        stmt = stmt.group_by(record_type_column)

        result = await self.session.execute(stmt)
        return {str(record_type): int(count) for record_type, count in result.all()}