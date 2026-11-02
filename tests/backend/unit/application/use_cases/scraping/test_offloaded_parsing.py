"""Every function a job sends through ComputeExecutor can cross a process boundary.

In the worker, parsing runs in child processes (ProcessPoolComputeExecutor), so each offloaded
callable and its arguments are pickled. A method bound to a service that holds a database or blob
client would fail there, so this guards the contract for every offloading call site.
"""
import pickle
from functools import partial
from pathlib import Path

from backend.application.use_cases.scraping.academic_calendar.profile import (
    AcademicCalendarProfile,
)
from backend.application.use_cases.scraping.academic_calendar.scrape.persistence import (
    parse_calendar_batch,
)
from backend.application.use_cases.scraping.websites.profile import WebsiteProfile
from backend.application.use_cases.scraping.websites.scrape.persistence import (
    parse_website_batch,
)
from backend.application.use_cases.scraping.wlu_registration.persistence import (
    parse_registration_sections,
)
from backend.domain.entities.scraping import ScrapePageRead, ScrapeStatus
from backend.domain.entities.wlu.lexicon_resolver import WluLexiconResolver
from goldenguide_common.config.loader import ConfigLoader
from tests.backend.unit.application.use_cases.scraping.websites.factories import (
    IGNORED_EXTENSIONS,
    WLU,
)

CONFIG_ROOT = Path(__file__).parents[6] / "configs"
HTML = b"<html><head><title>T</title></head><body><main><h1>Fees</h1><p>Tuition.</p><a href='/x'>x</a></main></body></html>"
PAGE = ScrapePageRead(
    id=1, url="https://www.wlu.ca/fees.html", site_name="wlu_ca", status=ScrapeStatus.SUCCESS.value,
    blob_key="k", content_hash="h", needs_persistence=True,
)


class PlaceholderSecrets:
    def get(self, key: str, default: str | None = None) -> str | None:
        known = {"APP_ENV": "development", "CONFIG_PATH": str(CONFIG_ROOT), "EMBEDDING_RUNTIME": "cpu"}
        if key.startswith("SERVICE_CLIENT__"):
            return None
        return known.get(key, default if default is not None else "1")


def lexicon():
    profile = ConfigLoader(PlaceholderSecrets()).load_app_config().catalog.text_enrichment.wlu_lexicon
    return WluLexiconResolver(profile), profile


def round_trip(fn, *args):
    """What ProcessPoolComputeExecutor sends to a child, rebuilt there and run."""
    return pickle.loads(pickle.dumps(partial(fn, *args)))()


def test_website_import_parsing_crosses_a_process_boundary():
    batch = round_trip(parse_website_batch, [PAGE], {"k": HTML}, WLU)
    assert [record.title for record in batch.records] == ["Fees"]


def test_calendar_import_parsing_crosses_a_process_boundary():
    resolver, profile = lexicon()
    batch = round_trip(parse_calendar_batch, [PAGE], {}, "2026/2027", resolver, profile)
    assert batch.skipped_pages == 1  # No blob: nothing parsed, but the call itself is picklable.


def test_registration_import_parsing_crosses_a_process_boundary():
    resolver, _ = lexicon()
    assert round_trip(parse_registration_sections, [], "202609", resolver) == ([], [])


def test_crawl_link_extraction_crosses_a_process_boundary():
    website = WebsiteProfile(WLU, IGNORED_EXTENSIONS)
    links = round_trip(website.extract_links, HTML.decode(), "https://www.wlu.ca/fees.html")
    assert "https://www.wlu.ca/x" in links
    # The calendar profile is pickled the same way; its links come from its own content root.
    assert round_trip(AcademicCalendarProfile().extract_links, "<html></html>", "https://example.edu/") == []
