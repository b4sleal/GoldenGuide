import pytest
from pydantic import ValidationError

from backend.domain.settings.institution import InstitutionProfile


def profile(**overrides) -> InstitutionProfile:
    fields = {"code": "EDU", "timezone": "America/Toronto", "registration_url": "https://registration.example.edu/"}
    return InstitutionProfile(**(fields | overrides))


def test_unknown_timezone_fails_at_startup():
    with pytest.raises(ValidationError, match="Unknown timezone"):
        profile(timezone="Mars/Olympus_Mons")
