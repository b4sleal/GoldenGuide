"""School (academic data) database port: one unit of work exposing the school repositories."""
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio.session import AsyncSession

from backend.domain.ports.repositories.school.course_page_repo import CourseRepository
from backend.domain.ports.repositories.school.course_term_repo import (
    CourseTermRepository,
)
from backend.domain.ports.repositories.school.scraping_repo import ScrapingRepository
from backend.domain.ports.repositories.school.wlu_page_repo import WluPageRepository


@dataclass(frozen=True,slots=True)
class SchoolRepositories:
    courses: CourseRepository
    course_terms: CourseTermRepository
    wlu_pages: WluPageRepository
    scraping: ScrapingRepository

class SchoolDB(Protocol):
    def start(
            self,
            session: AsyncSession | None = None,
    ) -> AbstractAsyncContextManager[SchoolRepositories]:
        ...