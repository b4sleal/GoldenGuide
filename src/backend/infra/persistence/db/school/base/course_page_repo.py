"""SQL course repository. Upsert overwrites and flags re-embedding on content change; insert_courses
never touches existing rows (used for LORIS-only courses so Academic Calendar data is not overwritten).
"""
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.entities.wlu.course import CourseBase, CourseCreate, CourseField, CourseUpdate, CourseRead
from backend.domain.ports.repositories.filters import CourseFilter
from backend.domain.ports.repositories.school.query_types import CoursePageParams
from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.school.filters import CourseFilterTranslator
from backend.infra.persistence.db.school.school_tables import Course
from backend.infra.persistence.db.utils.generic.db_ops import generic_fetch, generic_update
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting
from backend.infra.persistence.db.utils.generic.update_rules import overwrite_and_flag_reembed
from backend.infra.persistence.db.utils.generic.upsert_mapping import (
    column_name,
    mapped_table,
    prepare_rows,
    update_columns,
)


class SqlCourseRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps):
        self.session = session
        self.dialect = dialect
        self.aliases: dict[str, InstrumentedAttribute] = {}

    async def upsert_course(
            self,
            payload: CourseCreate,
    ) -> PrimaryKey:
        ids = await self.upsert_courses([payload])
        return ids[0]

    async def upsert_courses(
            self,
            payloads: list[CourseCreate],
    ) -> list[PrimaryKey]:
        identity = CourseBase.IDENTITY_FIELDS
        columns = update_columns(CourseUpdate, identity_fields=identity, aliases=self.aliases)

        return await self.dialect.upsert(
            self.session,
            table=mapped_table(Course),
            rows=prepare_rows(payloads, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
            build_updates=overwrite_and_flag_reembed(
                columns,
                embed_fields=CourseBase.EMBED_FIELDS,
                flag_field=CourseField.NEEDS_EMBEDDING,
                aliases=self.aliases,
            ),
        )

    async def insert_courses(
            self,
            payloads: list[CourseCreate],
    ) -> list[PrimaryKey]:
        """Insert unseen courses only; returns ids of the rows actually inserted."""
        identity = CourseBase.IDENTITY_FIELDS

        return await self.dialect.insert_ignore(
            self.session,
            table=mapped_table(Course),
            rows=prepare_rows(payloads, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
        )


    async def update_courses(
            self,
            course_ids: list[int],
            update_data: CourseUpdate,
    ) -> None:
        if not course_ids:
            return

        stmt = update(Course).where(Course.id.in_(course_ids))
        await generic_update(self.session, stmt, update_data, self.aliases)

    async def fetch_courses[T: BaseModel = CourseRead](
            self,
            page_params: CoursePageParams,
            filters: CourseFilter | None = None,
            *,
            view_model: type[T] = CourseRead,
    ) -> list[T]:
        stmt = select(Course)
        stmt = CourseFilterTranslator.apply(stmt, filters)
        stmt = apply_sorting(
            stmt=stmt,
            model=Course,
            order_by=page_params.order_by,
            aliases=self.aliases,
            stable_tiebreaker=CourseField.ID.value,
        )

        return await generic_fetch(
            session=self.session,
            stmt=stmt,
            db_model=Course,
            view_model=view_model,
            page_params=page_params,
            aliases=self.aliases,
        )

    async def count_courses(self, filters: CourseFilter | None = None) -> int:
        stmt = select(func.count()).select_from(Course)
        stmt = CourseFilterTranslator.apply(stmt, filters)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)