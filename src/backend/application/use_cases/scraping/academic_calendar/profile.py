"""Crawl rules for the WLU Academic Calendar, scoped to one academic year.

build_profile() reads the calendar home page to find that year's calendars (cal/y parameters), then
seeds the crawl with every page of each calendar's search results. Only URLs of those years are
followed; course URLs are normalized to a fixed parameter order so each course is stored once.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse, urlunparse, urljoin

import httpx
from bs4 import BeautifulSoup

from backend.application.services.simple_scraping.service import USER_AGENT
from backend.domain.entities.scraping import SiteProfile
from backend.domain.entities.wlu.academic_level import AcademicLevel
from backend.shared.utils.academic_year import get_current_academic_year
from backend.shared.utils.hashing import sha256_hash


class AcademicCalendarProfile:
    COURSE_PARAM_ORDER = ["c", "cal", "d", "s", "y"]
    SITE_NAME = "academic_calendar_wlu"
    ALLOWED_DOMAINS = ("academic-calendar.wlu.ca",)
    ROOT_URL = "https://academic-calendar.wlu.ca/"
    SEARCH_URL = ROOT_URL + "search.php?s_text=&pg={pg}&cal={cal}&y={y}"
    # The calendar shows this many search results per page (used when it omits "Page x of n").
    RESULTS_PER_PAGE = 100
    # The `cal` URL parameter names the calendar; the home page lists them as "<year> Undergraduate
    # Calendar" (cal=1) and "<year> Graduate Calendar" (cal=3). Migration 0006 froze this mapping.
    CALENDAR_LEVELS = {"1": AcademicLevel.UNDERGRADUATE, "3": AcademicLevel.GRADUATE}

    @classmethod
    def calendar_param(cls, url: str) -> str | None:
        return parse_qs(urlparse(url).query).get("cal", [None])[0]

    @classmethod
    def academic_level(cls, url: str) -> AcademicLevel | None:
        """The calendar's level for a calendar page URL; None when `cal` is missing or unknown."""
        return cls.CALENDAR_LEVELS.get(cls.calendar_param(url) or "")

    def __init__(self):
        self.allowed_year_params: set[str] = set()
        self.academic_year: str = "latest"

    def academic_calendar_is_target_year(self, url: str) -> bool:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)

        if not self.allowed_year_params:
            return False

        return any(y in self.allowed_year_params for y in query_params.get("y", []))

    def academic_calendar_is_noise_route(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        return path.endswith(("/search.php", "/search-adv.php", "/index_old.php", "/index.php"))

    def normalize_url(self, url: str) -> str:
        """Canonical form: first value per parameter, sorted (course pages: fixed order). A course URL
        without department and subject (d, s) is not a usable course page and becomes ""."""
        parsed = urlparse(url)
        path = parsed.path.lower()

        pairs = parse_qsl(parsed.query, keep_blank_values=False)
        query: dict[str, str] = {}
        for k, v in pairs:
            if k not in query:
                query[k] = v

        if path.endswith("/course.php"):
            if "d" not in query or "s" not in query:
                return ""

            ordered_pairs = [
                (key, query[key])
                for key in self.COURSE_PARAM_ORDER
                if key in query
            ]

            return urlunparse(
                (
                    parsed.scheme.lower(),
                    parsed.netloc.lower(),
                    parsed.path,
                    "",
                    urlencode(ordered_pairs),
                    "",
                )
            )

        ordered_pairs = sorted(query.items(), key=lambda item: item[0])

        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                "",
                urlencode(ordered_pairs),
                "",
            )
        )

    def extract_links(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        parsed = urlparse(base_url)
        path = parsed.path.lower()

        if path.endswith("/search.php"):
            root = soup.select_one("div.res")
        else:
            root = soup.select_one("div.content")

        if root is None:
            return []

        links: list[str] = []

        for tag in root.find_all("a", href=True):
            href = tag.get("href")
            if not href:
                continue

            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)

        return links

    def should_follow_url(self, url: str) -> bool:
        parsed = urlparse(url)

        if parsed.netloc.lower() not in self.ALLOWED_DOMAINS:
            return False

        if not self.academic_calendar_is_target_year(url):
            return False

        normalized = self.normalize_url(url)
        if parsed.path.lower().endswith("/course.php") and not normalized:
            return False

        return True

    def should_ingest_url(self, url: str) -> bool:
        parsed = urlparse(url)

        if parsed.netloc.lower() not in self.ALLOWED_DOMAINS:
            return False

        if not self.academic_calendar_is_target_year(url):
            return False

        if self.academic_calendar_is_noise_route(url):
            return False

        return True

    def get_blob_path(self, url: str) -> str:
        """
        Dynamically routes the HTML blob to the correct versioned S3/MinIO folder.
        e.g., academic-calendar/2026/2027/courses/<hash>.html
        """
        url_hash = sha256_hash(url)
        path = urlparse(url).path.lower()
        safe_version = self.academic_year.replace("/", "-")
        base_path = f"academic-calendar/{safe_version}"

        if path.endswith("/course.php"):
            return f"{base_path}/courses/{url_hash}.html"
        if path.endswith("/glossary.php"):
            return f"{base_path}/glossary/{url_hash}.html"
        if path.endswith("/search.php"):
            return f"{base_path}/search/{url_hash}.html"

        return f"{base_path}/pages/{url_hash}.html"

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> str:
        response = await client.get(url)
        response.raise_for_status()
        return response.text

    async def _resolve_calendar_links(
            self,
            client: httpx.AsyncClient,
            academic_year: str | None,
    ) -> list[tuple[str, str]]:
        """(cal, y) of every calendar listed under the academic year's heading (the newest year if None)."""
        html = await self._fetch_html(client, self.ROOT_URL)
        soup = BeautifulSoup(html, "html.parser")
        root = soup.select_one("div.content") or soup

        chosen_heading = None
        year_pattern = re.compile(r"\b\d{4}/\d{4}\b")

        if academic_year:
            for h2 in root.find_all("h2"):
                heading_text = h2.get_text(" ", strip=True)
                if academic_year in heading_text:
                    chosen_heading = h2
                    break

            if chosen_heading is None:
                raise ValueError(f"Academic year not found on main calendar page: {academic_year}")
        else:
            for h2 in root.find_all("h2"):
                heading_text = h2.get_text(" ", strip=True)
                if year_pattern.search(heading_text):
                    chosen_heading = h2
                    break

            if chosen_heading is None:
                raise ValueError("Could not find any academic year heading on main calendar page.")

        links: list[tuple[str, str]] = []
        current = chosen_heading.find_next_sibling()

        while current:
            if getattr(current, "name", None) == "h2":
                break

            if getattr(current, "name", None) == "ul":
                for a_tag in current.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    absolute = urljoin(self.ROOT_URL, href)

                    parsed = urlparse(absolute)
                    query = parse_qs(parsed.query)

                    cal = query.get("cal", [None])[0]
                    y = query.get("y", [None])[0]

                    if cal and y:
                        links.append((cal, y))
                break

            current = current.find_next_sibling()

        if not links:
            raise ValueError("Could not resolve calendar links for the selected academic year.")

        return links

    async def _discover_total_pages(
            self,
            client: httpx.AsyncClient,
            cal: str,
            y: str,
    ) -> int:
        """Number of search-result pages of one calendar (1 when the page does not say)."""
        html = await self._fetch_html(client, self.SEARCH_URL.format(pg=1, cal=cal, y=y))

        match = re.search(r"Page\s+\d+\s+of\s+(\d+)", html, re.IGNORECASE)
        if match:
            return int(match.group(1))

        results_match = re.search(r"<strong>\s*(\d+)\s*</strong>\s*results", html, re.IGNORECASE)
        if results_match:
            total_results = int(results_match.group(1))
            return max(1, -(-total_results // self.RESULTS_PER_PAGE))  # Ceiling division.

        return 1

    async def _build_seed_urls(
            self,
            client: httpx.AsyncClient,
            academic_year: str | None,
    ) -> tuple[str, ...]:
        calendar_links = await self._resolve_calendar_links(
            client=client,
            academic_year=academic_year,
        )

        self.allowed_year_params = {y for _, y in calendar_links}

        seed_urls: list[str] = []

        for cal, y in calendar_links:
            total_pages = await self._discover_total_pages(
                client=client,
                cal=cal,
                y=y,
            )

            for pg in range(1, total_pages + 1):
                seed_urls.append(self.SEARCH_URL.format(pg=pg, cal=cal, y=y))

        return tuple(seed_urls)

    async def build_profile(
            self,
            academic_year: str | None = None,
            timeout_seconds: int = 30,
    ) -> SiteProfile:
        self.academic_year = academic_year or get_current_academic_year()
        timeout = httpx.Timeout(timeout_seconds)

        async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
        ) as client:
            seed_urls = await self._build_seed_urls(
                client=client,
                academic_year=academic_year,
            )

        return SiteProfile(
            name=self.SITE_NAME,
            version=self.academic_year,
            seed_urls=seed_urls,
            allowed_domains=self.ALLOWED_DOMAINS,
            normalize_url=self.normalize_url,
            should_follow_url=self.should_follow_url,
            should_scrape_url=self.should_ingest_url,
            get_blob_path=self.get_blob_path,
            extract_links=self.extract_links,
        )