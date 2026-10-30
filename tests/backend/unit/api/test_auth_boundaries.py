from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.api.app import create_app
from backend.api.auth import LOCAL_ADMIN_SUBJECT, get_principal, require_admin
from backend.domain.entities.auth.principal import Principal, Role


def disabled_auth_request(*, local_admin: bool, peer: str | None = "172.30.0.4", headers: dict | None = None):
    """A request to a deployment with sign-in off, from `peer` (None: no client address)."""
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host=peer) if peer is not None else None,
        app=SimpleNamespace(state=SimpleNamespace(auth_mode="disabled", local_admin=local_admin)),
    )


@pytest.mark.asyncio
async def test_auth_disabled_fails_closed():
    with pytest.raises(HTTPException) as exc:
        await get_principal(disabled_auth_request(local_admin=False))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("peer", ["127.0.0.1", "::1", "172.30.0.4", "192.168.65.1"])
async def test_local_admin_allows_this_machine(peer):
    # Inside Docker, browser requests arrive from the Nginx container or the network gateway.
    principal = await get_principal(disabled_auth_request(local_admin=True, peer=peer))
    assert principal.subject == LOCAL_ADMIN_SUBJECT
    assert Role.ADMIN in principal.roles


@pytest.mark.asyncio
async def test_local_admin_refuses_the_public_tunnel():
    # Cloudflare stamps every request it forwards; the peer is still a private container address.
    request = disabled_auth_request(local_admin=True, headers={"cf-connecting-ip": "203.0.113.9"})
    with pytest.raises(HTTPException) as exc:
        await get_principal(request)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("peer", ["8.8.8.8", "100.101.102.103", "not-an-ip", None])
async def test_local_admin_refuses_other_peers(peer):
    # Public addresses, Tailscale peers (100.64.0.0/10 is not private), sockets, unknown peers.
    with pytest.raises(HTTPException) as exc:
        await get_principal(disabled_auth_request(local_admin=True, peer=peer))
    assert exc.value.status_code == 503


def test_local_admin_cannot_start_in_production():
    reader = SimpleNamespace(get=lambda key, default="": {
        "APP_ENV": "production", "SITE_ORIGIN": "https://askgoldenguide.ca", "LOCAL_ADMIN": "true",
    }.get(key, default))
    with pytest.raises(ValueError, match="LOCAL_ADMIN"):
        create_app(reader)


@pytest.mark.asyncio
async def test_unknown_cookie_cannot_authenticate():
    store = SimpleNamespace(get=AsyncMock(return_value=None))
    request = SimpleNamespace(headers={}, cookies={"gg_session": "unknown"}, app=SimpleNamespace(state=SimpleNamespace(
        auth_mode="oidc", session_store=store
    )))
    with pytest.raises(HTTPException) as exc:
        await get_principal(request)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_role_is_required_for_admin():
    with pytest.raises(HTTPException) as exc:
        await require_admin(Principal(subject="student", roles=frozenset({Role.STUDENT})))
    assert exc.value.status_code == 403
