"""OIDC provider responses fail closed; valid signed ID tokens still complete login.

Only provider HTTP and OAuth responses are substituted. Signature and claim validation run
through the real JOSE library so the tests cover the authentication boundary.
"""
from time import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import RSAKey

from backend.domain.settings.oidc import OIDCSettings
from backend.domain.settings.service_clients import ServiceClientSettings, hash_key
from backend.infra.security.oidc import authlib_client
from backend.infra.security.oidc.authlib_client import (
    AuthlibOIDCClient,
    _require_secure_url,
)

DISCOVERY = {
    "issuer": "https://idp.example.com",
    "authorization_endpoint": "https://idp.example.com/authorize",
    "token_endpoint": "https://idp.example.com/token",
    "jwks_uri": "https://idp.example.com/keys",
}
LOGIN = {"state": "test-state", "verifier": "v" * 64, "nonce": "test-nonce"}


@pytest.fixture
def oidc(oidc_policy):
    return AuthlibOIDCClient(OIDCSettings(
        discovery_url="https://idp.example.com/.well-known/openid-configuration",
        client_id="goldenguide", client_secret="", redirect_uri="https://app.example.com/callback",
        admin_role="admin",
    ), policy=oidc_policy)


@pytest.fixture
def provider_http(monkeypatch):
    client_type = httpx.AsyncClient

    def install(handler):
        monkeypatch.setattr(authlib_client.httpx, "AsyncClient", lambda **kwargs: client_type(
            transport=httpx.MockTransport(handler), **kwargs,
        ))

    return install


@pytest.fixture(scope="module")
def signing_key():
    key = RSAKey.generate_key(2048)
    key.ensure_kid()
    return key


def test_url_check_uses_the_injected_development_hosts(oidc_policy):
    with pytest.raises(ValueError, match="HTTPS"):
        _require_secure_url("http://other-provider.local/keys", "jwks_uri", oidc_policy.local_development_hosts)
    _require_secure_url("http://other-provider.local/keys", "jwks_uri", {"other-provider.local"})


@pytest.mark.parametrize("metadata", [{}, DISCOVERY | {"issuer": ""},
                                      DISCOVERY | {"token_endpoint": "http://idp.example.com/token"}])
async def test_invalid_discovery_never_initializes_provider(oidc, provider_http, metadata):
    provider_http(lambda request: httpx.Response(200, json=metadata))
    with pytest.raises(ValueError):
        await oidc.initialize()
    with pytest.raises(RuntimeError, match="not been initialized"):
        _ = oidc.metadata


async def test_discovery_network_failure_remains_an_outage(oidc, provider_http):
    def unavailable(request):
        raise httpx.ConnectError("provider unavailable", request=request)

    provider_http(unavailable)
    with pytest.raises(httpx.ConnectError):
        await oidc.initialize()


async def prepare_exchange(oidc, provider_http, monkeypatch, token, jwks):
    provider_http(lambda request: httpx.Response(
        200, json=jwks if request.url.path == "/keys" else DISCOVERY,
    ))
    await oidc.initialize()
    oauth = MagicMock()
    oauth.__aenter__ = AsyncMock(return_value=oauth)
    oauth.fetch_token = AsyncMock(return_value=token)
    monkeypatch.setattr(oidc, "_client", lambda state: oauth)


@pytest.mark.parametrize("token", [{}, {"id_token": 12}])
async def test_missing_or_malformed_id_token_is_rejected(oidc, provider_http, monkeypatch, token):
    await prepare_exchange(oidc, provider_http, monkeypatch, token, {"keys": []})
    with pytest.raises(ValueError):
        await oidc.exchange(code="test-code", **LOGIN)


@pytest.mark.parametrize("overrides,accepted", [
    ({}, True),
    ({"aud": ["goldenguide", "other"], "azp": "goldenguide"}, True),
    ({"nonce": "wrong"}, False), ({"iss": "https://other.example.com"}, False),
    ({"aud": "other"}, False),
    ({"aud": ["goldenguide", "other"]}, False), ({"azp": "other"}, False),
    ({"exp": 1}, False),
])
async def test_signed_tokens_require_valid_claims(
        oidc, provider_http, monkeypatch, signing_key, overrides, accepted,
):
    now = int(time())
    claims = {"iss": DISCOVERY["issuer"], "aud": "goldenguide", "sub": "student-123",
              "exp": now + 300, "iat": now, "nonce": LOGIN["nonce"]} | overrides
    token = jwt.encode({"alg": "RS256", "kid": signing_key.kid}, claims, signing_key)
    await prepare_exchange(oidc, provider_http, monkeypatch, {"id_token": token},
                           {"keys": [signing_key.as_dict(private=False)]})
    if accepted:
        assert await oidc.exchange(code="test-code", **LOGIN) == claims
    else:
        with pytest.raises((ValueError, JoseError)):
            await oidc.exchange(code="test-code", **LOGIN)


async def test_authorization_url_keeps_pkce_state_and_nonce(oidc, provider_http):
    from urllib.parse import parse_qs, urlparse

    provider_http(lambda request: httpx.Response(200, json=DISCOVERY))
    await oidc.initialize()
    query = parse_qs(urlparse(oidc.authorization_url(**LOGIN)).query)
    assert query["state"] == [LOGIN["state"]]
    assert query["nonce"] == [LOGIN["nonce"]]
    assert query["code_challenge_method"] == ["S256"]
    assert "code_challenge" in query


@pytest.mark.parametrize("mode", ["disabled", "oidc"])
def test_app_composition_injects_yaml_policy_only_when_oidc_is_enabled(monkeypatch, oidc_policy, mode):
    from backend.api import factory

    values = {
        "AUTH_MODE": mode, "SITE_ORIGIN": "https://app.example.com", "SERVE_FRONTEND": "false",
        "OIDC_DISCOVERY_URL": "https://idp.example.com/.well-known/openid-configuration",
        "OIDC_CLIENT_ID": "goldenguide", "OIDC_CLIENT_SECRET": "test-secret",
        "OIDC_REDIRECT_URI": "https://app.example.com/api/v1/auth/callback", "OIDC_ADMIN_ROLE": "admin",
    }
    container = MagicMock()
    container.secret_reader.return_value = SimpleNamespace(get=values.get)
    enabled = ServiceClientSettings(scopes=frozenset(), key_hashes=(hash_key("k"),))
    disabled = ServiceClientSettings(scopes=frozenset())
    container.app_config.return_value = SimpleNamespace(system=SimpleNamespace(
        oidc=oidc_policy, service_clients={"enabled": enabled, "disabled": disabled},
    ))
    monkeypatch.setattr(factory, "build_container", lambda: container)
    monkeypatch.setattr(factory.FastAPIInstrumentor, "instrument_app", lambda *args, **kwargs: None)

    app = factory.build_app()

    # Service clients are attached in either mode; one without key hashes is left out.
    assert set(app.state.service_clients) == {"enabled"}

    if mode == "oidc":
        assert isinstance(app.state.oidc, AuthlibOIDCClient)
        assert app.state.oidc.policy is oidc_policy
        assert app.state.oidc.settings.client_id == values["OIDC_CLIENT_ID"]
        assert app.state.oidc.settings.client_secret.get_secret_value() == values["OIDC_CLIENT_SECRET"]
        assert app.state.oidc.settings.redirect_uri == values["OIDC_REDIRECT_URI"]
    else:
        # The YAML is still read for service clients; only the OIDC client stays unbuilt.
        assert app.state.oidc is None
