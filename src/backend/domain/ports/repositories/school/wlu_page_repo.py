"""WLU page repository port."""
from typing import Protocol

from pydantic import BaseModel

from backend.domain.entities.wlu.wlu_pages import (
    WluPageCreate,
    WluPageRead,
    WluPageUpdate,
)
from backend.domain.ports.repositories.filters import WluPageFilter
from backend.domain.ports.repositories.school.query_types import WluPageParams
from backend.domain.ports.repositories.types import PrimaryKey


class WluPageRepository(Protocol):
    async def upsert_wlu_page(self, record: WluPageCreate) -> PrimaryKey: ...
    async def upsert_wlu_pages(self, records: list[WluPageCreate]) -> list[PrimaryKey]: ...

    async def fetch_records[T: BaseModel = WluPageRead](
            self,
            page_params: WluPageParams,
            filters: WluPageFilter | None = None,
            *,
            view_model: type[T] = WluPageRead
    ) -> list[T]: ...

    async def update_wlu_pages(
            self,
            page_ids: list[PrimaryKey],
            update_data: WluPageUpdate,
    ) -> None: ...


    async def count_all_records(self, filters: WluPageFilter | None = None) -> int: ...
    async def count_by_record_type(self, filters: WluPageFilter | None = None) -> dict[str, int]: ...