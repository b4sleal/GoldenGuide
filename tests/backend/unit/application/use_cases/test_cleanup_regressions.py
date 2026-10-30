"""Regressions: unparseable calendar course headers are skipped; a settings-cache outage is a cache miss."""
from backend.application.use_cases.scraping.academic_calendar.scrape.parse import parse_course_header
from backend.application.use_cases.settings.settings_cache import SettingsCacheService


def test_course_header_is_parsed():
    html = '<div class="content"><h1>CP120<br>Intro to Computing<br>0.5 Credit</h1></div>'

    assert parse_course_header(html) == ("CP", "120", "Intro to Computing", {"min": 0.5, "max": 0.5, "unit": "credits"})


def test_page_without_course_header_is_skipped_not_crashed():
    assert parse_course_header('<div class="content"><p>No heading</p></div>') is None
    assert parse_course_header('<div class="content"><h1>Course listing</h1></div>') is None
    assert parse_course_header("<html></html>") is None


class DownCache:
    async def get(self, key):
        raise ConnectionError("redis down")

    async def set(self, key, value, ttl=None):
        raise ConnectionError("redis down")


async def test_settings_cache_outage_reads_as_a_miss_and_writes_do_not_raise():
    cache = SettingsCacheService(DownCache())

    assert await cache.get() is None
    await cache.set({"version": 1})
