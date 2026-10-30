"""Crawl/scrape state: SiteProfile (a site's crawl rules), page statuses, and scrape_pages models."""
from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class FrozenScraping(BaseModel):
    model_config = ConfigDict(frozen=True)


class ScrapeStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    EMPTY = "empty"
    SKIPPED = "skipped"
    RETRYABLE_ERROR = "retryable_error"
    PERMANENT_ERROR = "permanent_error"


class CrawlMode(StrEnum):
    FRESH = "fresh"
    UPDATE = "update"
    RETRY = "retry"


class ScrapePageField(StrEnum):
    ID = "id"
    URL = "url"
    VERSION = "version"
    SITE_NAME = "site_name"
    STATUS = "status"
    HTTP_STATUS = "http_status"
    CONTENT_TYPE = "content_type"
    ERROR = "error"
    BLOB_KEY = "blob_key"
    CONTENT_HASH = "content_hash"
    ATTEMPTED_AT = "attempted_at"
    LAST_ATTEMPTED_AT = "last_attempted_at"
    LAST_SUCCESS_AT = "last_success_at"
    PARENT_URL = "parent_url"
    ETAG = "etag"
    LAST_MODIFIED_HEADER = "last_modified_header"
    RETRY_COUNT = "retry_count"
    NEEDS_PERSISTENCE = "needs_persistence"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


# Version of sites that are not published per academic year (one live copy of each page).
UNVERSIONED = "latest"


class SiteProfile(FrozenScraping):
    name: str
    version: str = UNVERSIONED
    seed_urls: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    normalize_url: Callable[[str], str]
    should_follow_url: Callable[[str], bool]
    should_scrape_url: Callable[[str], bool]
    get_blob_path: Callable[[str], str]
    extract_links: Callable[[str, str], list[str]]
    # A crawler honours robots.txt unless a site explicitly opts out (e.g. an approved internal crawl).
    respect_robots_txt: bool = True


class ScrapePageBase(FrozenScraping):
    IDENTITY_FIELDS: ClassVar[tuple[ScrapePageField, ...]] = (
        ScrapePageField.VERSION,
        ScrapePageField.URL,
    )

    url: str
    version: str = "latest" # academic calendar pages: 2026/2027, for generic just latest i guess
    site_name: str
    status: str
    http_status: int | None = None
    content_type: str | None = None
    error: str | None = None
    blob_key: str | None = None
    content_hash: str | None = None

    # 🛡️ PURE DATA: Removed the leaky command flags!
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_success_at: datetime | None = None
    retry_count: int = 0

    parent_url: str | None = Field(default=None, description="The URL that discovered this page")
    etag: str | None = None
    last_modified_header: str | None = None
    needs_persistence: bool = True

class ScrapePageCreate(ScrapePageBase):
    pass

class ScrapePageRead(ScrapePageBase):
    id: int

class ScrapePageUpdate(FrozenScraping):
    site_name: str | None = None
    status: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    error: str | None = None
    blob_key: str | None = None
    content_hash: str | None = None
    attempted_at: datetime | None = None
    last_success_at: datetime | None = None
    retry_count: int | None = None
    parent_url: str | None = None
    etag: str | None = None
    last_modified_header: str | None = None
    needs_persistence: bool | None = None

class ScrapePageCacheRead(FrozenScraping):
    """Minimal view strictly for HTTP/Blob caching logic."""
    url: str
    content_hash: str | None = None
    etag: str | None = None
    last_modified_header: str | None = None
    blob_key: str | None = None