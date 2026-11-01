"""The built frontend is served with a fallback to index.html for client-side routes only."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.spa import SpaStaticFiles

INDEX = "<!doctype html><title>GoldenGuide</title>"


@pytest.fixture
def client(tmp_path):
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = FastAPI()
    app.mount("/", SpaStaticFiles(tmp_path), name="frontend")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/", "/c/33333333-3333-4333-8333-333333333333"])
def test_app_routes_get_index(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.text == INDEX


def test_existing_asset_is_served(client):
    assert client.get("/assets/app.js").text == "console.log(1)"


@pytest.mark.parametrize("path", ["/assets/missing.js", "/api/v1/does-not-exist"])
def test_missing_assets_and_api_paths_stay_404(client, path):
    assert client.get(path).status_code == 404


def test_missing_build_fails_at_startup(tmp_path):
    with pytest.raises(RuntimeError, match="pnpm build"):
        SpaStaticFiles(tmp_path)
