"""AsyncCrawlerRunner gates every request (seeds, cached URLs, links, redirects) and its page budget."""
import re
from contextlib import asynccontextmanager

import httpx
import pytest

from backend.application.services.simple_scraping.service import AsyncCrawlerRunner
from backend.domain.entities.scraping import CrawlMode, ScrapeStatus, SiteProfile
from backend.shared.utils.hashing import sha256_hash
from tests.backend.unit.application.inline_compute import InlineCompute

HOST = "www.example.edu"
HREF = re.compile(r'href="([^"]+)"')
ROOT = f"https://{HOST}"


def html(*links: str) -> str:
    return "<html><body>" + "".join(f'<a href="{link}">x</a>' for link in links) + "</body></html>"


class FakeScraping:
    def __init__(self, cached: list[dict]):
        self.cached = cached
        self.saved = []

    async def fetch_pages(self, page_params, filters, view_model):
        rows = [
            row for row in self.cached
            if row["site_name"] == filters.site_name
            and (filters.status is None or row["status"] == filters.status)
            and (filters.statuses is None or row["status"] in filters.statuses)
        ]
        return [view_model(**row) for row in rows[page_params.offset:page_params.offset + page_params.limit]]

    async def upsert_scrape_pages(self, batch):
        self.saved.extend(batch)


class FakeSchoolDB:
    def __init__(self, cached=()):
        self.scraping = FakeScraping(list(cached))

    @asynccontextmanager
    async def start(self):
        yield self


class FakeBlobs:
    def __init__(self):
        self.uploaded = {}

    async def upload(self, key, data, content_type):
        self.uploaded[key] = data


class Site:
    """A fake website: path -> response, recording every request."""

    def __init__(self, pages: dict[str, httpx.Response], robots: httpx.Response | Exception | None = None):
        self.pages = pages
        self.robots = robots if robots is not None else httpx.Response(404)
        self.requested: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            if isinstance(self.robots, Exception):
                raise self.robots
            return self.robots
        self.requested.append(str(request.url))
        return self.pages.get(str(request.url), httpx.Response(404, headers={"content-type": "text/html"}))


def page(*links: str) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/html"}, text=html(*links))


def profile(seeds=(f"{ROOT}/a",), respect_robots_txt=True, **overrides) -> SiteProfile:
    fields = dict(
        name="example", seed_urls=tuple(seeds), allowed_domains=(HOST,),
        normalize_url=lambda url: url.split("#")[0],
        should_follow_url=lambda url: httpx.URL(url).host == HOST and "/excluded" not in url,
        should_scrape_url=lambda url: True,
        get_blob_path=lambda url: f"blobs/{url}",
        extract_links=lambda text, base: [str(httpx.URL(base).join(href)) for href in HREF.findall(text)],
        respect_robots_txt=respect_robots_txt,
    )
    return SiteProfile(**(fields | overrides))


async def crawl(site: Site, site_profile: SiteProfile, mode=CrawlMode.FRESH, cached=(), blobs=None, **kwargs):
    school_db = FakeSchoolDB(cached)
    runner = AsyncCrawlerRunner(school_db, blobs or FakeBlobs(), InlineCompute(), batch_size=1, transport=httpx.MockTransport(site))
    result = await runner.run_site(site_profile, mode=mode.value, concurrency=2, **kwargs)
    return result, {row.url: row for row in school_db.scraping.saved}


DISALLOW_PRIVATE = httpx.Response(200, text="User-agent: *\nDisallow: /private\n")


async def test_links_are_followed_within_the_rules():
    site = Site({f"{ROOT}/a": page("/b", "/excluded/c", "https://elsewhere.org/d"), f"{ROOT}/b": page()})

    _, saved = await crawl(site, profile())

    assert sorted(site.requested) == [f"{ROOT}/a", f"{ROOT}/b"]
    assert saved[f"{ROOT}/b"].status == ScrapeStatus.SUCCESS


async def test_robots_disallowed_seeds_and_links_are_never_requested():
    site = Site({f"{ROOT}/a": page("/private/x")}, robots=DISALLOW_PRIVATE)

    result, _ = await crawl(site, profile(seeds=(f"{ROOT}/a", f"{ROOT}/private/seed")))

    assert site.requested == [f"{ROOT}/a"]
    assert result["urls_disallowed"] == 1


@pytest.mark.parametrize("mode, status", [
    (CrawlMode.UPDATE, ScrapeStatus.SUCCESS),
    (CrawlMode.RETRY, ScrapeStatus.RETRYABLE_ERROR),
])
async def test_cached_urls_are_rechecked_against_robots_and_rules(mode, status):
    cached = [
        {"site_name": "example", "url": url, "status": status.value}
        for url in (f"{ROOT}/a", f"{ROOT}/private/old", f"{ROOT}/excluded/old")
    ]
    site = Site({f"{ROOT}/a": page()}, robots=DISALLOW_PRIVATE)

    await crawl(site, profile(), mode=mode, cached=cached)

    assert site.requested == [f"{ROOT}/a"]


async def test_a_site_may_opt_out_of_robots_txt():
    site = Site({f"{ROOT}/private/seed": page()}, robots=httpx.Response(200, text="User-agent: *\nDisallow: /\n"))

    await crawl(site, profile(seeds=(f"{ROOT}/private/seed",), respect_robots_txt=False))

    assert site.requested == [f"{ROOT}/private/seed"]


@pytest.mark.parametrize("robots, fetched", [
    (httpx.Response(404), True),                 # No robots.txt: everything allowed.
    (httpx.Response(503), False),                # Unreachable: nothing allowed.
    (httpx.ConnectError("down"), False),         # Network failure: never silently allowed.
])
async def test_robots_fetch_outcomes(robots, fetched):
    site = Site({f"{ROOT}/a": page()}, robots=robots)

    await crawl(site, profile())

    assert (site.requested == [f"{ROOT}/a"]) is fetched


async def test_page_limit_caps_every_request_including_seeds():
    seeds = [f"{ROOT}/s{i}" for i in range(10)]
    site = Site({url: page("/more1", "/more2") for url in seeds})

    await crawl(site, profile(seeds=seeds), page_limit=3)

    assert len(site.requested) == 3


async def test_redirects_outside_the_rules_are_not_followed():
    site = Site({
        f"{ROOT}/a": httpx.Response(302, headers={"location": "https://elsewhere.org/landing"}),
        f"{ROOT}/b": httpx.Response(301, headers={"location": "/private/x"}),
    }, robots=DISALLOW_PRIVATE)

    result, saved = await crawl(site, profile(seeds=(f"{ROOT}/a", f"{ROOT}/b")))

    assert sorted(site.requested) == [f"{ROOT}/a", f"{ROOT}/b"]  # Targets never requested.
    assert result["redirects_blocked"] == 2
    assert saved[f"{ROOT}/a"].status == ScrapeStatus.SKIPPED
    assert "elsewhere.org" in saved[f"{ROOT}/a"].error
    assert saved[f"{ROOT}/a"].blob_key is None


async def test_allowed_redirects_are_followed_and_stored_under_the_final_url():
    site = Site({f"{ROOT}/old": httpx.Response(301, headers={"location": "/new"}), f"{ROOT}/new": page()})

    _, saved = await crawl(site, profile(seeds=(f"{ROOT}/old",)))

    assert site.requested == [f"{ROOT}/old", f"{ROOT}/new"]
    assert saved[f"{ROOT}/new"].status == ScrapeStatus.SUCCESS


async def test_redirect_loops_stop():
    site = Site({f"{ROOT}/loop": httpx.Response(302, headers={"location": "/loop"})})

    _, saved = await crawl(site, profile(seeds=(f"{ROOT}/loop",)))

    assert "redirects" in saved[f"{ROOT}/loop"].error


async def test_documents_and_error_pages_are_not_parsed_for_links():
    extracted = []
    site = Site({
        f"{ROOT}/paper.cgi": httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7"),
        f"{ROOT}/gone": httpx.Response(404, headers={"content-type": "text/html"}, text=html("/from-404")),
    })
    spying = profile(
        seeds=(f"{ROOT}/paper.cgi", f"{ROOT}/gone"),
        extract_links=lambda text, base: extracted.append(base) or [],
    )

    _, saved = await crawl(site, spying)

    assert extracted == []
    assert saved[f"{ROOT}/paper.cgi"].status == ScrapeStatus.PERMANENT_ERROR
    assert f"{ROOT}/from-404" not in site.requested


async def test_redirect_hops_count_against_page_limit():
    site = Site({f"{ROOT}/a": httpx.Response(302, headers={"location": "/b"}), f"{ROOT}/b": page()})

    _, saved = await crawl(site, profile(seeds=(f"{ROOT}/a",)), page_limit=1)

    assert site.requested == [f"{ROOT}/a"]
    assert "page_limit" in saved[f"{ROOT}/a"].error


async def test_a_redirect_to_a_page_crawled_on_its_own_does_not_store_it_twice():
    site = Site({f"{ROOT}/old": httpx.Response(301, headers={"location": "/new"}), f"{ROOT}/new": page()})
    school_db = FakeSchoolDB()
    runner = AsyncCrawlerRunner(school_db, FakeBlobs(), InlineCompute(), batch_size=100, transport=httpx.MockTransport(site))

    await runner.run_site(profile(seeds=(f"{ROOT}/new", f"{ROOT}/old")), concurrency=1)

    urls = [row.url for row in school_db.scraping.saved]
    assert sorted(urls) == [f"{ROOT}/new", f"{ROOT}/old"]  # One row each; /new fetched once.
    assert site.requested.count(f"{ROOT}/new") == 1


async def test_after_a_redirect_the_final_urls_cache_decides_the_blob_upload():
    body = html()
    # The original URL's cached hash equals the new content's; the final URL was never stored.
    cached = [{"site_name": "example", "url": f"{ROOT}/old", "status": ScrapeStatus.SUCCESS.value,
               "content_hash": sha256_hash(body), "blob_key": f"blobs/{ROOT}/old"}]
    site = Site({f"{ROOT}/old": httpx.Response(301, headers={"location": "/new"}),
                 f"{ROOT}/new": httpx.Response(200, headers={"content-type": "text/html"}, text=body)})
    blobs = FakeBlobs()

    await crawl(site, profile(), mode=CrawlMode.UPDATE, cached=cached, blobs=blobs)

    assert f"blobs/{ROOT}/new" in blobs.uploaded


async def test_link_extraction_runs_through_the_compute_executor():
    site = Site({f"{ROOT}/a": page("/b"), f"{ROOT}/b": page()})
    compute = InlineCompute()
    runner = AsyncCrawlerRunner(FakeSchoolDB(), FakeBlobs(), compute, batch_size=1, transport=httpx.MockTransport(site))

    await runner.run_site(profile(), mode=CrawlMode.FRESH.value, concurrency=1)

    # One offloaded parse per fetched HTML page; the discovered link was still followed.
    assert len(compute.calls) == 2
    assert site.requested == [f"{ROOT}/a", f"{ROOT}/b"]
