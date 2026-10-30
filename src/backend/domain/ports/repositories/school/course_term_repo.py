"""Course-term (LORIS section) repository port, plus room/instructor lookups for entity matching."""
from typing import Protocol

from pydantic import BaseModel

from backend.domain.entities.wlu.loris_registration import (
    CourseFaculty,
    CourseTermCreate,
    CourseTermRead,
    CourseTermUpdate,
    MeetingRoom,
)
from backend.domain.ports.repositories.filters import CourseTermFilter
from backend.domain.ports.repositories.school.query_types import CourseTermParams
from backend.domain.ports.repositories.types import PrimaryKey


class CourseTermRepository(Protocol):
    async def upsert_course_term(self, payload: CourseTermCreate,) -> PrimaryKey: ...
    async def upsert_course_terms(self, payloads: list[CourseTermCreate]) -> list[PrimaryKey]: ...
    async def fetch_course_terms[T: BaseModel = CourseTermRead](
            self,
            page_params: CourseTermParams,
            filters: CourseTermFilter,
            *,
            view_model: type[T] = CourseTermRead
    ) -> list[T]: ...

    async def count_course_terms(self, filters: CourseTermFilter | None = None) -> int: ...

    async def fetch_meeting_rooms(self) -> list[MeetingRoom]:
        """Every distinct room any section meets in."""
        ...

    async def fetch_instructors(self) -> list[CourseFaculty]:
        """Every distinct instructor (bannerId, displayName) teaching any section."""
        ...

    async def update_course_terms(
            self,
            course_term_ids: list[PrimaryKey],
            update_data: CourseTermUpdate,
    ) -> None: ...
