"""CI must fail when integration dependencies were accidentally left unconfigured."""

import pytest


@pytest.mark.parametrize(
    "variable", ["GOLDENGUIDE_TEST_DATABASE_URL", "REDIS_TEST_URL", "QDRANT_TEST_URL"]
)
def test_required_service_cannot_be_silently_skipped(
    monkeypatch, infra_service_url, variable
):
    monkeypatch.setenv("GOLDENGUIDE_REQUIRE_TEST_SERVICES", "1")
    monkeypatch.delenv(variable, raising=False)

    with pytest.raises(pytest.fail.Exception, match=variable):
        infra_service_url(variable)
