"""Crawl rules for one configured university website (see WebsiteScrapeSettings)."""
from __future__ import annotations

from urllib.parse import urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx
import structlog
from bs4 import BeautifulSoup

from backend.application.services.simple_scraping.service import USER_AGENT
from backend.domain.entities.scraping import UNVERSIONED, SiteProfile
from backend.domain.settings.scraping import WebsiteScrapeSettings
from backend.shared.utils.hashing import sha256_hash

logger = structlog.get_logger()

SITEMAP_NAMESPACE = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# A sitemap index lists sitemaps; real sites nest one level, this bounds a misconfigured loop.
MAX_SITEMAP_DEPTH = 3
MAX_SITEMAP_REDIRECTS = 5
WEB_SCHEMES = ("http", "https")
NON_PAGE_HREFS = ("#", "javascript:", "mailto:", "tel:")


class WebsiteProfile:
    BLOB_PREFIX = "websites"

    def __init__(
            self,
            settings: WebsiteScrapeSettings,
            ignored_extensions: tuple[str, ...],
            transport: httpx.AsyncBaseTransport | None = None,  # Tests inject httpx.MockTransport.
    ) -> None:
        self.settings = settings
        self.ignored_extensions = ignored_extensions
        self.transport = transport
        self.sitemap_failures: list[str] = []

    def normalize_url(self, url: str) -> str:
        """Lowercase scheme and host, drop the query and fragment. Non-web URLs become "".

        University pages are static: query strings are tracking (?ref=...) and only duplicate pages.
        """
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in WEB_SCHEMES or not parts.netloc:
            return ""
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", "", ""))

    def should_follow_url(self, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path.lower()

        if parts.netloc.lower() not in self.settings.allowed_domains:
            return False
        if any(pattern.lower() in path for pattern in self.settings.excluded_path_patterns):
            return False
        return not path.endswith(self.ignored_extensions)

    def should_scrape_url(self, url: str) -> bool:
        # Every page the crawl may visit is content; exclusions already apply to both.
        return self.should_follow_url(url)

    def get_blob_path(self, url: str) -> str:
        return f"{self.BLOB_PREFIX}/{self.settings.site_name}/{sha256_hash(url)}.html"

    def extract_links(self, html: str, base_url: str) -> list[str]:
        """Links from the whole page: navigation in the header/footer helps discovery."""
        soup = BeautifulSoup(html, "html.parser")
        return [
            urljoin(base_url, href)
            for tag in soup.find_all("a", href=True)
            if (href := tag["href"].strip()) and not href.lower().startswith(NON_PAGE_HREFS)
        ]

    async def build_profile(self, timeout_seconds: int = 30) -> SiteProfile:
        async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,  # Followed by hand: every hop must stay on the site's hosts.
                headers={"User-Agent": USER_AGENT},
                transport=self.transport,
        ) as client:
            sitemap_pages = await self._sitemap_pages(client)

        return SiteProfile(
            name=self.settings.site_name,
            version=UNVERSIONED,
            seed_urls=tuple(dict.fromkeys((*self.settings.seed_urls, *sitemap_pages))),
            allowed_domains=self.settings.allowed_domains,
            normalize_url=self.normalize_url,
            should_follow_url=self.should_follow_url,
            should_scrape_url=self.should_scrape_url,
            get_blob_path=self.get_blob_path,
            extract_links=self.extract_links,
            respect_robots_txt=self.settings.respect_robots_txt,
        )

    async def _sitemap_pages(self, client: httpx.AsyncClient) -> list[str]:
        """Page URLs from the configured sitemaps, following sitemap indexes.

        A sitemap that cannot be read is recorded in sitemap_failures (and logged) instead of
        failing the crawl: pages it lists can still be reached through links.
        """
        self.sitemap_failures = []
        pages: list[str] = []
        visited: set[str] = set()
        pending = [(url, 0) for url in self.settings.sitemap_urls]

        while pending:
            sitemap_url, depth = pending.pop(0)
            if sitemap_url in visited or depth >= MAX_SITEMAP_DEPTH:
                continue
            visited.add(sitemap_url)

            try:
                response = await self._fetch_on_site(client, sitemap_url)
                response.raise_for_status()
                root = ElementTree.fromstring(response.content)
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
                logger.warning("sitemap_unreadable", site_name=self.settings.site_name, url=sitemap_url, error=str(exc))
                self.sitemap_failures.append(sitemap_url)
                continue

            locations = [loc.text.strip() for loc in root.iter(f"{SITEMAP_NAMESPACE}loc") if loc.text]
            if root.tag == f"{SITEMAP_NAMESPACE}sitemapindex":
                pending.extend((location, depth + 1) for location in locations)
                continue

            for location in locations:
                normalized = self.normalize_url(location)
                if normalized and self.should_follow_url(normalized):
                    pages.append(normalized)

        return pages

    def _on_site(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme.lower() in WEB_SCHEMES and parts.netloc.lower() in self.settings.allowed_domains

    async def _fetch_on_site(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """GET a sitemap, following redirects only within the site's own hosts.

        Sitemaps (including those an index lists) never leave the site: a foreign host, such as
        the Academic Calendar, is rejected before any request is made to it.
        """
        for _ in range(MAX_SITEMAP_REDIRECTS + 1):
            if not self._on_site(url):
                raise ValueError(f"sitemap outside the site's hosts: {url}")
            response = await client.get(url)
            if not response.is_redirect:
                return response
            url = urljoin(str(response.url), response.headers["location"])
        raise ValueError(f"more than {MAX_SITEMAP_REDIRECTS} sitemap redirects")
