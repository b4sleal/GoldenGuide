"""Website crawl/import endpoints are mounted under the admin router and need the sources scope."""
import pytest
from fastapi.testclient import TestClient

from backend.api.auth import get_principal, require_same_origin
from backend.domain.entities.auth.principal import Scope
from backend.domain.settings.service_clients import ServiceClientSettings, hash_key

INDEXING_KEY = "indexing-only-key"


def all_calls(dependant) -> set:
    """Every dependency callable of a route, including nested ones."""
    calls = set()
    for dependency in dependant.dependencies:
        calls.add(dependency.call)
        calls |= all_calls(dependency)
    return calls


@pytest.mark.parametrize("path", ["/websites/discover", "/websites/import"])
def test_website_endpoints_require_an_authenticated_same_origin_caller(app, path):
    [route] = [route for route in app.routes if getattr(route, "path", "").endswith(f"/sources{path}")]
    assert {get_principal, require_same_origin} <= all_calls(route.dependant)


@pytest.mark.parametrize("path", ["/websites/discover", "/websites/import"])
def test_website_endpoints_reject_a_client_without_the_sources_scope(app, path):
    app.state.service_clients = {
        "indexer": ServiceClientSettings(scopes=frozenset({Scope.INDEXING_SYNC}), key_hashes=(hash_key(INDEXING_KEY),)),
    }
    with TestClient(app) as client:
        response = client.post(f"/api/v1/admin/sources{path}", headers={"Authorization": f"Bearer {INDEXING_KEY}"})
    assert response.status_code == 403
