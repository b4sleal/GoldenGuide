"""EmbeddingSource for WLU pages, plus the page <-> vector source_id mapping ("page_<id>")."""
from backend.domain.entities.ingestion_types import KnowledgeSourceType, VectorSource, WluPageVectorPayload
from backend.domain.entities.wlu.wlu_pages import WluPageRead, WluPageUpdate
from backend.domain.ports.repositories.school.query_types import WluPageParams, WluPageSortField
from backend.domain.ports.repositories.sorting import SortSpec
from backend.domain.ports.repositories.types import PrimaryKey


PAGE_SOURCE_ID_PREFIX = "page_"


def page_source_id(page_id: PrimaryKey) -> str:
    """The vector source_id of a wlu_pages row: "page_<id>"."""
    return f"{PAGE_SOURCE_ID_PREFIX}{page_id}"


def page_id_of(source_id: str) -> int | None:
    """The wlu_pages id a vector source_id names, or None if it is not a page's."""
    if not source_id.startswith(PAGE_SOURCE_ID_PREFIX):
        return None
    suffix = source_id[len(PAGE_SOURCE_ID_PREFIX):]
    return int(suffix) if suffix.isdigit() else None


class WluPageEmbeddingSource:
    """WLU pages (Academic Calendar programs, glossary, and website pages) for EmbeddingJob."""
    name = VectorSource.WLU_PAGES

    async def count(self, repos) -> int:
        return await repos.wlu_pages.count_all_records()

    async def fetch(self, repos, offset: int, limit: int) -> list[WluPageRead]:
        return await repos.wlu_pages.fetch_records(
            page_params=WluPageParams(limit=limit, offset=offset, order_by=[SortSpec(field=WluPageSortField.ID)]),
            view_model=WluPageRead,
        )

    def record_id(self, record: WluPageRead) -> PrimaryKey:
        return record.id

    def needs_embedding(self, record: WluPageRead) -> bool:
        return record.needs_embedding

    def payload(self, page: WluPageRead) -> WluPageVectorPayload:
        return WluPageVectorPayload(
            content=page.content or "",
            title=page.title,
            source_id=page_source_id(page.id),
            embedding_source=self.name,
            url=page.url,
            source_type=KnowledgeSourceType.WLU_PAGE,
            site_name=page.site_name,
            record_type=page.record_type,
        )

    async def set_needs_embedding(self, repos, ids: list[PrimaryKey], value: bool) -> None:
        await repos.wlu_pages.update_wlu_pages(page_ids=ids, update_data=WluPageUpdate(needs_embedding=value))
