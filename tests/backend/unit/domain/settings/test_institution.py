import pytest
from pydantic import ValidationError

from backend.domain.settings.institution import InstitutionProfile


def profile(**overrides) -> InstitutionProfile:
    fields = {"code": "EDU", "timezone": "America/Toronto", "registration_url": "https://registration.example.edu/"}
    return InstitutionProfile(**(fields | overrides))


def test_unknown_timezone_fails_at_startup():
    with pytest.raises(ValidationError, match="Unknown timezone"):
        profile(timezone="Mars/Olympus_Mons")


def test_registration_url_must_be_http():
    with pytest.raises(ValidationError):
        profile(registration_url="not a url")


def test_zone_is_the_configured_timezone():
    assert profile().zone.key == "America/Toronto"
