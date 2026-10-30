"""SQL course-term repository: sections as aggregates with meeting and faculty child rows,
plus the distinct rooms and instructors used for entity matching.
"""
from pydantic import BaseModel
from sqlalchemy import func, select

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.entities.wlu.loris_registration import (
    CourseTermBase,
    CourseTermCreate,
    CourseTermField,
    CourseFaculty,
    CourseTermRead,
    MeetingRoom,
)
from backend.domain.ports.repositories.filters import CourseTermFilter
from backend.domain.ports.repositories.school.query_types import CourseTermParams
from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.dialects.ops import SqlDialectOps
from backend.infra.persistence.db.school.filters import CourseTermFilterTranslator
from backend.infra.persistence.db.school.school_tables import CourseTerm, CourseTermFaculty, CourseTermMeeting
from backend.infra.persistence.db.utils.generic.aggregates import (
    child_collections,
    update_aggregate,
    upsert_aggregate,
)
from backend.infra.persistence.db.utils.generic.sorting import apply_sorting
from backend.infra.persistence.db.utils.generic.update_rules import overwrite_and_flag_reembed
from backend.infra.persistence.db.utils.generic.upsert_mapping import (
    column_name,
    prepare_rows,
    update_columns,
)
from backend.domain.entities.wlu.loris_registration import CourseTermUpdate
from backend.infra.persistence.db.utils.generic.db_ops import generic_fetch

class SqlCourseTermRepository:
    def __init__(self, session: AsyncSession, dialect: SqlDialectOps):
        self.session = session
        self.dialect = dialect
        self.aliases: dict[str, InstrumentedAttribute] = {}

    async def upsert_course_term(
            self,
            payload: CourseTermCreate,
    ) -> PrimaryKey:
        ids = await self.upsert_course_terms([payload])
        return ids[0]

    async def upsert_course_terms(
            self,
            payloads: list[CourseTermCreate],
    ) -> list[PrimaryKey]:
        identity = CourseTermBase.IDENTITY_FIELDS
        # Meetings and faculty are child rows, replaced by upsert_aggregate rather than SET columns.
        columns = tuple(
            column for column in update_columns(CourseTermUpdate, identity_fields=identity, aliases=self.aliases)
            if column not in child_collections(CourseTerm)
        )

        return await upsert_aggregate(
            self.session,
            self.dialect,
            model=CourseTerm,
            rows=prepare_rows(payloads, identity_fields=identity, aliases=self.aliases),
            conflict_columns=[column_name(field.value, self.aliases) for field in identity],
            build_updates=overwrite_and_flag_reembed(
                columns,
                embed_fields=CourseTermBase.EMBED_FIELDS,
                flag_field=CourseTermField.NEEDS_EMBEDDING,
                aliases=self.aliases,
            ),
        )

    async def fetch_course_terms[T: BaseModel = CourseTermRead](
            self,
            page_params: CourseTermParams,
            filters: CourseTermFilter | None = None,
            *,
            view_model: type[T] = CourseTermRead
    ) -> list[T]:
        stmt = select(CourseTerm)
        stmt = CourseTermFilterTranslator.apply(stmt, filters)

        stmt = apply_sorting(
            stmt=stmt,
            model=CourseTerm,
            order_by=page_params.order_by,
            aliases=self.aliases,
            stable_tiebreaker=CourseTermField.ID.value,
        )

        return await generic_fetch(
            session=self.session,
            stmt=stmt,
            db_model=CourseTerm,
            view_model=view_model,
            page_params=page_params,
            aliases=self.aliases,
        )

    async def count_course_terms(self, filters: CourseTermFilter | None = None) -> int:
        stmt = select(func.count()).select_from(CourseTerm)
        stmt = CourseTermFilterTranslator.apply(stmt, filters)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def fetch_meeting_rooms(self) -> list[MeetingRoom]:
        building, room = CourseTermMeeting.building, CourseTermMeeting.room

        stmt = (
            select(building, room)
            .where(room.is_not(None), room != "")
            .distinct()
            .order_by(building, room)
        )
        rows = await self.session.execute(stmt)
        return [MeetingRoom(building=row[0], room=row[1]) for row in rows]

    async def fetch_instructors(self) -> list[CourseFaculty]:
        banner_id, name = CourseTermFaculty.bannerId, CourseTermFaculty.displayName

        # One row per bannerId (the identity); its name is taken from any section listing it.
        stmt = (
            select(banner_id, func.max(name))
            .where(banner_id.is_not(None), name.is_not(None), name != "")
            .group_by(banner_id)
            .order_by(banner_id)
        )
        rows = await self.session.execute(stmt)
        return [CourseFaculty(bannerId=row[0], displayName=row[1]) for row in rows]

    async def update_course_terms(
            self,
            course_term_ids: list[PrimaryKey],
            update_data: CourseTermUpdate,
    ) -> None:
        if not course_term_ids:
            return

        await update_aggregate(self.session, CourseTerm, course_term_ids, update_data, self.aliases)
