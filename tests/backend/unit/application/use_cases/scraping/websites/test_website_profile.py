"""Which URLs a website crawl visits, and how sitemaps seed it."""
import httpx
import pytest

from backend.application.use_cases.scraping.websites.profile import WebsiteProfile
from backend.domain.entities.scraping import UNVERSIONED
from tests.backend.unit.application.use_cases.scraping.websites.factories import IGNORED_EXTENSIONS, SCHOLARS, WLU

URLSET = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>"""
INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</sitemapindex>"""


def urlset(*locs):
    return URLSET.format("".join(f"<url><loc>\n  {loc}\n</loc></url>" for loc in locs))


def index(*locs):
    return INDEX.format("".join(f"<sitemap><loc>{loc}</loc></sitemap>" for loc in locs))


def wlu(transport=None) -> WebsiteProfile:
    return WebsiteProfile(WLU, IGNORED_EXTENSIONS, transport=transport)


@pytest.mark.parametrize("url, expected", [
    ("https://WWW.WLU.CA/about/index.html#top", "https://www.wlu.ca/about/index.html"),
    ("https://www.wlu.ca/a.html?z=1&a=2", "https://www.wlu.ca/a.html"),
    ("https://www.wlu.ca", "https://www.wlu.ca/"),
    ("mailto:someone@wlu.ca", ""),
    ("javascript:void(0)", ""),
])
def test_normalize_url(url, expected):
    assert wlu().normalize_url(url) == expected


@pytest.mark.parametrize("url, expected", [
    ("https://www.wlu.ca/about/index.html", True),
    ("https://wlu.ca/about/index.html", True),
    ("https://www.wlu.ca/news/2026/story.html", False),
    ("https://www.wlu.ca/about/governance/board/news/item.html", False),  # /news/ anywhere in the path.
    ("https://www.wlu.ca/documents/handbook.PDF", False),                # Not an HTML page.
    ("https://academic-calendar.wlu.ca/course.php?c=1", False),          # The calendar has its own scraper.
    ("https://students.wlu.ca/academics/index.html", False),            # Another configured site.
])
def test_follow_and_scrape_rules(url, expected):
    profile = wlu()
    assert profile.should_follow_url(url) is expected
    assert profile.should_scrape_url(url) is expected


def test_full_text_downloads_are_excluded_on_scholars():
    profile = WebsiteProfile(SCHOLARS, IGNORED_EXTENSIONS)
    assert profile.should_follow_url("https://scholars.wlu.ca/etd/2412/") is True
    assert profile.should_follow_url("https://scholars.wlu.ca/cgi/viewcontent.cgi?article=1&context=etd") is False


def test_links_come_from_the_whole_page_and_skip_non_page_hrefs():
    html = """<header><a href="/nav">Nav</a></header><main><a href="#top">Top</a>
              <a href="mailto:a@wlu.ca">Mail</a><a href="page.html">Page</a></main>"""
    assert wlu().extract_links(html, "https://www.wlu.ca/about/") == [
        "https://www.wlu.ca/nav", "https://www.wlu.ca/about/page.html",
    ]


def test_blob_path_is_per_site():
    assert wlu().get_blob_path("https://www.wlu.ca/a").startswith("websites/wlu_ca/")


async def test_sitemap_pages_seed_the_crawl_after_the_configured_seeds():
    responses = {"https://www.wlu.ca/sitemap.xml": urlset(
        "https://www.wlu.ca/about/index.html",
        "https://www.wlu.ca/news/story.html",       # Excluded before it ever becomes a seed.
        "https://elsewhere.org/page.html",          # Foreign locations are dropped.
        "https://www.wlu.ca/home.html",             # Duplicate of a configured seed.
    )}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=responses[str(request.url)]))

    site_profile = await wlu(transport).build_profile()

    assert site_profile.seed_urls == ("https://www.wlu.ca/home.html", "https://www.wlu.ca/about/index.html")
    assert site_profile.name == "wlu_ca"
    assert site_profile.version == UNVERSIONED
    assert site_profile.respect_robots_txt is True


async def test_sitemap_indexes_are_followed_and_unreadable_sitemaps_reported():
    responses = {
        "https://scholars.wlu.ca/siteindex.xml": index(
            "https://scholars.wlu.ca/etd/sitemap.xml", "https://scholars.wlu.ca/broken/sitemap.xml",
        ),
        "https://scholars.wlu.ca/etd/sitemap.xml": urlset("https://scholars.wlu.ca/etd/1/"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body = responses.get(str(request.url))
        return httpx.Response(200, text=body) if body else httpx.Response(500)

    profile = WebsiteProfile(SCHOLARS, IGNORED_EXTENSIONS, transport=httpx.MockTransport(handler))
    site_profile = await profile.build_profile()

    assert site_profile.seed_urls == ("https://scholars.wlu.ca/etd/1/",)
    assert profile.sitemap_failures == ["https://scholars.wlu.ca/broken/sitemap.xml"]


async def test_malformed_sitemap_xml_is_reported_not_raised():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<urlset><url>"))
    profile = wlu(transport)

    site_profile = await profile.build_profile()

    assert site_profile.seed_urls == ("https://www.wlu.ca/home.html",)
    assert profile.sitemap_failures == ["https://www.wlu.ca/sitemap.xml"]


async def test_sitemaps_never_leave_the_sites_hosts():
    requested = []
    responses = {
        "https://www.wlu.ca/sitemap.xml": httpx.Response(200, text=index(
            "https://academic-calendar.wlu.ca/sitemap.xml", "https://www.wlu.ca/moved.xml",
        )),
        "https://www.wlu.ca/moved.xml": httpx.Response(301, headers={"location": "https://elsewhere.org/s.xml"}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return responses[str(request.url)]

    profile = wlu(httpx.MockTransport(handler))
    await profile.build_profile()

    assert requested == ["https://www.wlu.ca/sitemap.xml", "https://www.wlu.ca/moved.xml"]
    assert profile.sitemap_failures == ["https://academic-calendar.wlu.ca/sitemap.xml", "https://www.wlu.ca/moved.xml"]


async def test_sitemap_redirects_within_the_site_are_followed():
    responses = {
        "https://www.wlu.ca/sitemap.xml": httpx.Response(301, headers={"location": "https://wlu.ca/sitemap-new.xml"}),
        "https://wlu.ca/sitemap-new.xml": httpx.Response(200, text=urlset("https://www.wlu.ca/about/index.html")),
    }
    profile = wlu(httpx.MockTransport(lambda request: responses[str(request.url)]))

    site_profile = await profile.build_profile()

    assert "https://www.wlu.ca/about/index.html" in site_profile.seed_urls
