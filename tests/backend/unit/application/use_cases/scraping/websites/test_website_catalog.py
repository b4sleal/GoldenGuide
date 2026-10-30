"""The website catalog loads from YAML and is validated at startup."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.domain.settings.scraping import ScrapingCatalog, Website
from goldenguide_common.config.loader import ConfigLoader
from tests.backend.unit.application.use_cases.scraping.websites.factories import SCHOLARS, WLU

CONFIG_ROOT = Path(__file__).parents[7] / "configs"


class PlaceholderSecrets:
    def get(self, key: str, default: str | None = None) -> str | None:
        known = {"APP_ENV": "development", "CONFIG_PATH": str(CONFIG_ROOT), "EMBEDDING_RUNTIME": "cpu"}
        if key.startswith("SERVICE_CLIENT__"):
            return None  # Unset, as by default: those clients are disabled (a placeholder is not a valid hash).
        return known.get(key, "1")


def test_every_website_is_configured_with_its_content_rules():
    scraping = ConfigLoader(PlaceholderSecrets()).load_app_config().catalog.scraping

    assert set(scraping.websites) == set(Website)
    wlu, students, scholars = (scraping.websites[site] for site in Website)
    assert (wlu.content_selector, wlu.remove_selectors) == ("main", ("header", "footer"))
    assert "/news/" in wlu.excluded_path_patterns and "/news/" in students.excluded_path_patterns
    assert scholars.content_selector == "#content"
    assert all(settings.respect_robots_txt for settings in scraping.websites.values())
    assert ".pdf" in scraping.ignored_extensions
    # The Academic Calendar is never crawled from here.
    assert not any("academic-calendar" in host for s in scraping.websites.values() for host in s.allowed_domains)


def test_a_website_without_settings_fails_at_startup():
    with pytest.raises(ValidationError, match="missing from the scraping catalog"):
        ScrapingCatalog(websites={Website.WLU: WLU})


def test_site_names_must_be_unique():
    with pytest.raises(ValidationError, match="own site_name"):
        ScrapingCatalog(websites={Website.WLU: WLU, Website.STUDENTS_WLU: WLU, Website.SCHOLARS_WLU: SCHOLARS})
