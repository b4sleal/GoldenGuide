"""Service clients: bearer keys with scopes, alongside signed-in administrators."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from omegaconf import OmegaConf
from pydantic import ValidationError
from structlog.testing import capture_logs

from backend.api.auth import get_principal, require_same_origin, require_scope
from backend.core.startup.service_key import env_name
from backend.domain.entities.auth.principal import Principal, Role, Scope
from backend.domain.settings.service_clients import ServiceClientSettings, hash_key
from backend.domain.settings.system_settings import SystemSettings

KEY = "current-key"
PREVIOUS_KEY = "previous-key"
NIGHTLY = ServiceClientSettings(
    scopes=frozenset({Scope.SOURCES_COLLECT, Scope.INDEXING_SYNC}),
    key_hashes=(hash_key(KEY), hash_key(PREVIOUS_KEY)),
)


def request(headers=None, cookies=None, auth_mode="oidc", clients=None, session=None):
    return SimpleNamespace(
        headers=headers or {}, cookies=cookies or {}, method="POST", url=SimpleNamespace(path="/api/v1/admin/x"),
        app=SimpleNamespace(state=SimpleNamespace(
            auth_mode=auth_mode, service_clients={"nightly": NIGHTLY} if clients is None else clients,
            session_store=SimpleNamespace(get=AsyncMock(return_value=session)), site_origin="https://site",
        )),
    )


def bearer(key: str) -> dict[str, str]:
    return {"authorization": f"Bearer {key}"}


# ---- settings -------------------------------------------------------------------------------------

def test_unset_secrets_disable_a_client_and_bad_hashes_fail_at_boot():
    assert ServiceClientSettings(scopes=frozenset(), key_hashes=[None, "  "]).key_hashes == ()
    with pytest.raises(ValidationError):
        ServiceClientSettings(scopes=frozenset(), key_hashes=["not-a-sha256"])


def test_current_and_previous_keys_are_accepted_others_are_not():
    assert NIGHTLY.accepts(KEY) and NIGHTLY.accepts(PREVIOUS_KEY)
    assert not NIGHTLY.accepts("someone-elses-key")


def test_yaml_client_is_disabled_until_its_hash_secret_is_set():
    config = OmegaConf.load(Path(__file__).parents[4] / "configs/base/system_config.yml")
    OmegaConf.register_new_resolver("secrets", lambda key, default=None: default, replace=True)
    system = SystemSettings.model_validate(OmegaConf.to_container(config.system, resolve=True))

    nightly = system.service_clients["github_actions_nightly"]
    assert nightly.key_hashes == ()
    assert nightly.scopes == {Scope.SOURCES_COLLECT, Scope.INDEXING_SYNC, Scope.JOBS_READ}
    codegen = system.service_clients["openapi_codegen"]
    assert codegen.key_hashes == ()
    assert codegen.scopes == {Scope.DOCS_READ}  # Schema only: it can run no admin route.


@pytest.mark.parametrize("client", ["github_actions_nightly", "openapi_codegen"])
def test_key_tool_names_the_secret_the_yaml_reads(client):
    yaml = (Path(__file__).parents[4] / "configs/base/system_config.yml").read_text(encoding="utf-8")
    assert f"${{secrets:{env_name(client)}}}" in yaml


# ---- authentication -------------------------------------------------------------------------------

async def test_a_valid_key_is_its_client_with_only_its_scopes():
    principal = await get_principal(request(headers=bearer(KEY)))
    assert principal.subject == "service:nightly"
    assert principal.roles == frozenset()
    assert principal.has_scope(Scope.INDEXING_SYNC) and not principal.has_scope(Scope.SETTINGS_WRITE)


async def test_bearer_keys_work_with_sign_in_disabled():
    principal = await get_principal(request(headers=bearer(KEY), auth_mode="disabled"))
    assert principal.subject == "service:nightly"


@pytest.mark.parametrize("headers", [bearer("wrong"), {"authorization": "Bearer "}, {"authorization": "bearer"}])
async def test_bad_or_empty_keys_are_401(headers):
    with pytest.raises(HTTPException) as exc:
        await get_principal(request(headers=headers))
    assert exc.value.status_code == 401


async def test_a_bad_key_never_falls_back_to_a_valid_session_cookie():
    admin_session = SimpleNamespace(subject="admin", roles=["admin"])
    with pytest.raises(HTTPException) as exc:
        await get_principal(request(headers=bearer("wrong"), cookies={"gg_session": "s"}, session=admin_session))
    assert exc.value.status_code == 401


async def test_without_configured_clients_every_key_is_401():
    with pytest.raises(HTTPException) as exc:
        await get_principal(request(headers=bearer(KEY), clients={}))
    assert exc.value.status_code == 401


async def test_audit_logs_name_the_client_and_never_contain_the_key():
    with capture_logs() as logs:
        await get_principal(request(headers=bearer(KEY)))
        with pytest.raises(HTTPException):
            await get_principal(request(headers=bearer("wrong-secret")))
    assert [log["event"] for log in logs] == ["service_client_authenticated", "service_client_rejected"]
    assert logs[0]["client"] == "nightly"
    assert KEY not in str(logs) and "wrong-secret" not in str(logs)


# ---- authorization ---------------------------------------------------------------------------------

async def test_administrators_hold_every_scope():
    admin = Principal(subject="admin", roles=frozenset({Role.ADMIN}))
    for scope in Scope:
        assert await require_scope(scope)(admin) is admin


async def test_a_client_without_the_scope_is_403():
    client = Principal(subject="service:x", roles=frozenset(), scopes=frozenset({Scope.INDEXING_SYNC}))
    with pytest.raises(HTTPException) as exc:
        await require_scope(Scope.SETTINGS_WRITE)(client)
    assert exc.value.status_code == 403


async def test_same_origin_applies_to_cookie_requests_not_bearer_requests():
    with pytest.raises(HTTPException) as exc:
        await require_same_origin(request(cookies={"gg_session": "s"}))
    assert exc.value.status_code == 403
    assert await require_same_origin(request(headers=bearer(KEY))) is None


# ---- through the real admin routes ------------------------------------------------------------------

def scoped_app() -> FastAPI:
    app = FastAPI()
    app.state.service_clients = {"nightly": NIGHTLY}
    app.state.auth_mode = "disabled"
    app.state.site_origin = "https://site"

    @app.post("/sync", dependencies=[Depends(require_same_origin), Depends(require_scope(Scope.INDEXING_SYNC))])
    async def sync():
        return {"started": True}

    return app


def test_a_scheduled_caller_can_start_a_job_without_an_origin_header():
    with TestClient(scoped_app()) as client:
        assert client.post("/sync", headers=bearer(KEY)).json() == {"started": True}


def test_settings_stay_closed_to_the_nightly_client(app):
    app.state.service_clients = {"nightly": NIGHTLY}
    with TestClient(app) as client:
        assert client.get("/api/v1/admin/settings/", headers=bearer(KEY)).status_code == 403
        assert client.post("/api/v1/admin/indexing/pages/sync", headers=bearer("wrong")).status_code == 401
        # No key and sign-in disabled: fails closed as before.
        assert client.post("/api/v1/admin/indexing/pages/sync").status_code == 503
