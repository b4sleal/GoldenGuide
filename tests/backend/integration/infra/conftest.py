"""Optional locally, mandatory in CI: missing services must never produce a green test gate."""

import os
from collections.abc import Callable

import pytest


@pytest.fixture(scope="session")
def infra_service_url() -> Callable[[str], str]:
    def require(variable: str) -> str:
        value = os.getenv(variable)
        if value:
            return value
        message = f"{variable} is not configured for infra integration tests"
        if os.getenv("GOLDENGUIDE_REQUIRE_TEST_SERVICES") == "1":
            pytest.fail(message)
        pytest.skip(message)

    return require
