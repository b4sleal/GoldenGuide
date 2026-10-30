"""Same-origin (CSRF) guard and rate-limit client identification."""
from ipaddress import ip_network
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.auth import require_same_origin
from backend.api.middleware.simple_rate_limit import _client_address

SITE = "http://localhost:8080"


def _request(method="POST", headers=None, client_host="203.0.113.5", proxies=()):
    state = SimpleNamespace(site_origin=SITE, trusted_proxy_networks=[ip_network(p) for p in proxies])
    return SimpleNamespace(
        method=method,
        headers=headers or {},
        client=SimpleNamespace(host=client_host) if client_host else None,
        app=SimpleNamespace(state=state),
    )


@pytest.mark.asyncio
async def test_safe_methods_skip_origin_check():
    await require_same_origin(_request(method="GET"))


@pytest.mark.asyncio
async def test_same_origin_write_allowed():
    await require_same_origin(_request(headers={"origin": SITE}))


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"origin": "https://evil.example"}])
async def test_missing_or_foreign_origin_write_rejected(headers):
    with pytest.raises(HTTPException) as exc:
        await require_same_origin(_request(headers=headers))
    assert exc.value.status_code == 403


def test_forwarded_ip_ignored_from_untrusted_peer():
    request = _request(headers={"cf-connecting-ip": "198.51.100.9"})
    assert _client_address(request) == "203.0.113.5"


def test_forwarded_ip_used_from_trusted_proxy():
    request = _request(headers={"cf-connecting-ip": "198.51.100.9"}, client_host="10.0.0.2", proxies=["10.0.0.0/8"])
    assert _client_address(request) == "198.51.100.9"


def test_malformed_forwarded_ip_from_trusted_proxy_rejected():
    request = _request(headers={"cf-connecting-ip": "not-an-ip"}, client_host="10.0.0.2", proxies=["10.0.0.0/8"])
    with pytest.raises(HTTPException) as exc:
        _client_address(request)
    assert exc.value.status_code == 400


def test_missing_peer_uses_shared_bucket():
    assert _client_address(_request(client_host=None)) == "unknown"
