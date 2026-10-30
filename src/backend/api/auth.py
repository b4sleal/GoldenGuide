"""Authorization dependencies for routes.

Two ways to authenticate, never mixed in one request:
    - People sign in (routes/identity.py), which produces a server-side session cookie.
      Never infer student status from a successful login alone; roles come only from the
      session, which identity.py builds from explicitly configured identity-provider roles.
    - Machine callers send "Authorization: Bearer <key>" for a configured service client
      (domain/settings/service_clients.py) and get only that client's scopes.
These dependencies resolve the caller and decide what it may do.
"""
from collections.abc import Awaitable, Callable
from ipaddress import ip_address

import structlog
from fastapi import Depends, HTTPException, Request

from backend.domain.entities.auth.principal import Principal, Role, Scope

logger = structlog.get_logger(__name__)

# Every role GoldenGuide understands. Unknown roles in a session are ignored, not rejected,
# so adding a role in the identity provider cannot break sign-in.
_KNOWN_ROLES = frozenset(Role)

# Methods that must not change state; cross-origin checks only apply to the others.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_BEARER_SCHEME = "bearer"
SERVICE_SUBJECT_PREFIX = "service:"
LOCAL_ADMIN_SUBJECT = "local:admin"

# Cloudflare's edge sets this on every request it forwards, so its presence marks public traffic.
_CLOUDFLARE_CLIENT_HEADER = "cf-connecting-ip"


def _is_local_request(request: Request) -> bool:
    """True for requests from this machine: not through the public tunnel, from a loopback or private peer.

    Inside Docker the peer is the Nginx container or the network gateway, never 127.0.0.1, so an
    address check alone cannot tell "this machine" apart. This relies on published ports binding to
    loopback (the default *_BIND_ADDRESS): then the only route from outside is the Cloudflare
    tunnel, whose requests always carry the header checked first.
    """
    if _CLOUDFLARE_CLIENT_HEADER in request.headers or request.client is None:
        return False
    try:
        peer = ip_address(request.client.host)
    except ValueError:
        return False
    return peer.is_loopback or peer.is_private


def _bearer_key(request: Request) -> str | None:
    """The key of an "Authorization: Bearer <key>" header ('' if empty), or None without one."""
    scheme, _, key = request.headers.get("authorization", "").partition(" ")
    return key.strip() if scheme.lower() == _BEARER_SCHEME else None


def _service_principal(request: Request, key: str) -> Principal:
    """The service client owning `key`, or 401. A bearer request never falls back to the session cookie."""
    for name, client in request.app.state.service_clients.items():
        if key and client.accepts(key):
            logger.info("service_client_authenticated", client=name, method=request.method, path=request.url.path)
            return Principal(subject=f"{SERVICE_SUBJECT_PREFIX}{name}", roles=frozenset(), scopes=client.scopes)

    logger.warning("service_client_rejected", method=request.method, path=request.url.path)
    raise HTTPException(401, "Invalid service key")


async def get_principal(request: Request) -> Principal:
    """Resolve the caller from a service key or the session cookie, or fail closed."""
    # Step 1: machine callers. Independent of AUTH_MODE, so scheduled jobs work without sign-in.
    key = _bearer_key(request)
    if key is not None:
        return _service_principal(request, key)

    # Step 2: if sign-in is turned off, only this machine can be an administrator, and only when
    # LOCAL_ADMIN opts in (refused in production at startup). Everyone else gets 503 rather than
    # 401, because signing in would not help: the deployment is not configured for it.
    if request.app.state.auth_mode != "oidc":
        if request.app.state.local_admin and _is_local_request(request):
            return Principal(subject=LOCAL_ADMIN_SUBJECT, roles=frozenset({Role.ADMIN}))
        raise HTTPException(503, "Authentication is not configured")

    # Step 3: no cookie means anonymous.
    session_id = request.cookies.get("gg_session")
    if not session_id:
        raise HTTPException(401, "Authentication required")

    # Step 4: look the session up server-side. If the session store (Redis) is down, this
    # raises and the request fails with a 5xx: an outage must never grant access.
    session = await request.app.state.session_store.get(session_id)
    if session is None:
        raise HTTPException(401, "Session expired or revoked")

    # Step 5: convert stored role strings into the domain Role enum.
    return Principal(
        subject=session.subject,
        roles=frozenset(Role(role) for role in session.roles if role in _KNOWN_ROLES),
    )


async def require_student(principal: Principal = Depends(get_principal)) -> Principal:
    """Allow only sessions carrying the student role."""
    if Role.STUDENT not in principal.roles:
        raise HTTPException(403, "Student access required")
    return principal


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    """Allow only signed-in administrators (people, not service clients)."""
    if Role.ADMIN not in principal.roles:
        raise HTTPException(403, "Administrator access required")
    return principal


def require_scope(scope: Scope) -> Callable[..., Awaitable[Principal]]:
    """Dependency allowing callers holding `scope`: administrators, or service clients granted it."""
    async def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has_scope(scope):
            raise HTTPException(403, f"Missing scope: {scope.value}")
        return principal

    return dependency


async def require_same_origin(request: Request) -> None:
    """Reject state-changing requests that did not come from our own site (CSRF defense in depth).

    The session cookie is already SameSite=Lax, which stops most cross-site POSTs. This check
    also covers browsers/edge cases where Lax is not enough. Browsers always send Origin on
    POST/PATCH/DELETE, so a missing Origin is treated as foreign.

    Bearer requests are exempt: they authenticate only by their header (get_principal never reads
    the cookie for them), and another site cannot make a browser send that header (CORS).
    """
    if request.method in _SAFE_METHODS or _bearer_key(request) is not None:
        return
    if request.headers.get("origin") != request.app.state.site_origin:
        raise HTTPException(403, "Cross-origin request denied")
