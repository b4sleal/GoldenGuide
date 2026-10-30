"""Scrape-page repository port: crawl results and persistence flags."""
from typing import Protocol

from pydantic import BaseModel

from backend.domain.entities.scraping import (
    ScrapePageCreate,
    ScrapePageField,
    ScrapePageRead,
    ScrapePageUpdate,
)
from backend.domain.ports.repositories.filters import ScrapePageFilter
from backend.domain.ports.repositories.school.query_types import ScrapePageParams
from backend.domain.ports.repositories.types import PrimaryKey


class ScrapingRepository(Protocol):
    # Renamed to strictly match standard CRUD semantics
    async def upsert_scrape_pages(self, payloads: list[ScrapePageCreate]) -> list[PrimaryKey]: ...

    async def fetch_pages[T: BaseModel = ScrapePageRead](
            self,
            page_params: ScrapePageParams,
            filters: ScrapePageFilter | None = None,
            *,
            view_model: type[T] = ScrapePageRead,
    ) -> list[T]: ...

    async def update_scrape_pages(
            self,
            page_ids: list[int],
            update_data: ScrapePageUpdate,
    ) -> None: ...

    async def count_pages(self, filters: ScrapePageFilter | None = None) -> int: ...

    async def count_pages_by(
            self,
            field: ScrapePageField,
            filters: ScrapePageFilter | None = None,
    ) -> dict[str, int]: ...