"""SQL document repository."""
from pydantic import BaseModel
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.entities.documents import DocumentCreate, DocumentUpdate, DocumentRead, DocumentBase, DocumentField
from backend.domain.ports.repositories.filters import DocumentFilter
from backend.domain.ports.repositories.app.query_types import DocumentPageParams
from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.app.app_tables import AppDocumentTable
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.utils.generic.db_ops import generic_update, generic_fetch
from backend.infra.persistence.db.utils.generic.update_rules import overwrite
from backend.infra.persistence.db.utils.generic.upsert_mapping import update_columns, prepare_rows, column_name, mapped_table
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting
from backend.infra.persistence.db.app.filters import DocumentFilterTranslator

class SqlDocumentRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps):
        self.session = session
        self.dialect = dialect
        self.aliases: dict[str, InstrumentedAttribute] = {}

    async def upsert_documents(self, documents: list[DocumentCreate]) -> list[PrimaryKey]:
        identity = DocumentBase.IDENTITY_FIELDS
        columns = update_columns(DocumentUpdate, identity_fields=identity, aliases=self.aliases)

        return await self.dialect.upsert(
            self.session,
            table=mapped_table(AppDocumentTable),
            rows=prepare_rows(documents, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
            build_updates=lambda existing, incoming: overwrite(incoming, columns),
        )

    async def update_document(self, document_id: str, update_data: DocumentUpdate) -> None:
        stmt = update(AppDocumentTable).where(AppDocumentTable.document_id == document_id)
        await generic_update(self.session, stmt, update_data, self.aliases)
        await self.session.flush()

    async def fetch_documents[T: BaseModel = DocumentRead](
            self,
            page_params: DocumentPageParams,
            filters: DocumentFilter | None = None,
            *,
            view_model: type[T] = DocumentRead
    ) -> list[T]:
        stmt = select(AppDocumentTable)
        stmt = DocumentFilterTranslator.apply(stmt, filters)
        stmt = apply_sorting(
            stmt=stmt,
            model=AppDocumentTable,
            order_by=page_params.order_by,
            aliases=self.aliases,
            stable_tiebreaker=DocumentField.DOCUMENT_ID.value,
        )

        return await generic_fetch(
            session=self.session,
            stmt=stmt,
            db_model=AppDocumentTable,
            view_model=view_model,
            page_params=page_params,
            aliases=self.aliases,
        )

    async def delete_document(self, document_id: str) -> None:
        stmt = delete(AppDocumentTable).where(AppDocumentTable.document_id == document_id)
        await self.session.execute(stmt)
        await self.session.flush()