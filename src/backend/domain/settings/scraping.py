"""Which university websites are crawled into wlu_pages, and how (catalogs/scraping/websites.yml)."""
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrozenScrapingSettings(BaseModel):
    model_config = ConfigDict(frozen=True)


class Website(StrEnum):
    """A crawlable website; its rules live in the scraping catalog under this key."""
    WLU = "wlu"
    STUDENTS_WLU = "students_wlu"
    SCHOLARS_WLU = "scholars_wlu"


class WebsiteScrapeSettings(FrozenScrapingSettings):
    """
    Crawl and content rules for one website whose pages are stored as plain WLU pages
    (title + body text), with no structured extraction.
    """
    site_name: str = Field(min_length=1, description="scrape_pages / wlu_pages site_name, e.g. wlu_ca.")
    allowed_domains: tuple[str, ...] = Field(min_length=1, description="Hosts that are crawled; others are ignored.")
    sitemap_urls: tuple[str, ...] = Field(default=(), description="Sitemaps or sitemap indexes seeding the crawl.")
    seed_urls: tuple[str, ...] = Field(default=(), description="Extra start pages (sitemaps are not exhaustive).")
    content_selector: str = Field(min_length=1, description="CSS selector of the page's content root.")
    remove_selectors: tuple[str, ...] = Field(default=(), description="Noise removed inside the content root.")
    excluded_path_patterns: tuple[str, ...] = Field(
        default=(), description="URLs whose path contains any of these are neither crawled nor stored.",
    )
    title_suffix: str | None = Field(default=None, description="Site suffix stripped from <title>.")
    respect_robots_txt: bool = Field(default=True, description="Skip URLs the site's robots.txt disallows.")

    @field_validator("allowed_domains")
    @classmethod
    def lowercase_hosts(cls, hosts: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(host.lower() for host in hosts)


type WebsiteCatalog = Mapping[Website, WebsiteScrapeSettings]


class ScrapingCatalog(FrozenScrapingSettings):
    websites: WebsiteCatalog
    ignored_extensions: tuple[str, ...] = Field(
        default=(), description="File extensions never crawled (documents, media): not HTML pages.",
    )

    @field_validator("ignored_extensions")
    @classmethod
    def lowercase_extensions(cls, extensions: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(extension.lower() for extension in extensions)

    @field_validator("websites")
    @classmethod
    def every_website_configured(cls, websites: WebsiteCatalog) -> WebsiteCatalog:
        # Fail at startup, not when an administrator first runs that site's crawl.
        missing = sorted(set(Website) - set(websites))
        if missing:
            raise ValueError(f"Websites missing from the scraping catalog: {missing}")
        site_names = [settings.site_name for settings in websites.values()]
        if len(set(site_names)) != len(site_names):
            raise ValueError("Each website needs its own site_name (it scopes scrape_pages and wlu_pages).")
        return websites
