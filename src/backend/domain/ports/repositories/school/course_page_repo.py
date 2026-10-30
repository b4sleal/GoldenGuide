"""Course repository port (insert-only and upsert paths are distinct on purpose)."""
from typing import Protocol

from pydantic import BaseModel

from backend.domain.entities.wlu.course import CourseCreate, CourseRead, CourseUpdate
from backend.domain.ports.repositories.filters import CourseFilter
from backend.domain.ports.repositories.school.query_types import CoursePageParams
from backend.domain.ports.repositories.types import PrimaryKey


class CourseRepository(Protocol):
    async def upsert_course(self, payload: CourseCreate,) -> PrimaryKey: ...
    async def upsert_courses(self, payloads: list[CourseCreate],) -> list[PrimaryKey]: ...
    async def insert_courses(self, payloads: list[CourseCreate],) -> list[PrimaryKey]: ...

    async def update_courses(
            self,
            course_ids: list[PrimaryKey],
            update_data: CourseUpdate,
    ) -> None: ...

    async def fetch_courses[T: BaseModel = CourseRead](
            self,
            page_params: CoursePageParams,
            filters: CourseFilter | None = None,
            *,
            view_model: type[T] = CourseRead,
    ) -> list[T]: ...

    async def count_courses(
            self,
            filters: CourseFilter | None = None,
    ) -> int: ...