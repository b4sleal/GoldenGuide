"""OIDC browser sign-in (authorization code + PKCE). Public chat does not depend on this router.

Flow:
    /login    -> store a one-time transaction, redirect to the identity provider (Keycloak / Entra)
    /callback -> verify state, exchange the code, create a server-side session, set the session cookie
    /me       -> who is signed in
    /logout   -> revoke the session and clear the cookie
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from joserfc.errors import JoseError

from backend.api.auth import require_same_origin
from backend.domain.entities.auth.storage import AuthSession, OAuthTransaction

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Lifetimes in seconds. The login transaction only needs to survive the trip to the provider and back.
LOGIN_TRANSACTION_SECONDS = 300
SESSION_SECONDS = 604800 # 1 week login time


def _enabled(request: Request) -> None:
    """404 when sign-in is turned off, so the endpoints behave as if they do not exist."""
    if request.app.state.auth_mode != "oidc":
        raise HTTPException(404, "Sign-in is not enabled")


def _cookie_options(request: Request) -> dict:
    """Cookie flags: not readable by JS, HTTPS-only when the site is HTTPS, sent on top-level navigation."""
    return {
        "httponly": True,
        "secure": request.app.state.site_origin.startswith("https://"),
        "samesite": "lax",
        "path": "/",
    }


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    _enabled(request)

    # Step 1: fresh random values for this attempt.
    #   state    -> ties the callback to this browser (CSRF protection for the login itself)
    #   nonce    -> ties the ID token to this attempt (prevents token replay)
    #   verifier -> PKCE secret; proves the code is redeemed by whoever started the login
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)

    # Step 2: keep the secrets server-side (Redis), keyed by state, valid for a few minutes.
    settings = request.app.state.oidc.settings
    transaction = OAuthTransaction(redirect_uri=settings.redirect_uri, code_verifier=verifier, nonce=nonce)
    await request.app.state.oauth_transaction_store.create(state, transaction, LOGIN_TRANSACTION_SECONDS)

    # Step 3: send the browser to the identity provider, remembering state in a short-lived cookie.
    url = request.app.state.oidc.authorization_url(state=state, verifier=verifier, nonce=nonce)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie("gg_oidc_state", state, max_age=LOGIN_TRANSACTION_SECONDS, **_cookie_options(request))
    return response


@router.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    _enabled(request)

    # Step 1: the state in the URL must match the cookie this browser got at /login.
    # Checked before touching Redis so forged callbacks cost nothing.
    state = request.query_params.get("state")
    browser_state = request.cookies.get("gg_oidc_state")
    code = request.query_params.get("code")
    if not state or not browser_state or not secrets.compare_digest(state, browser_state) or not code:
        raise HTTPException(400, "Invalid OIDC callback state")

    # Step 2: atomically take the transaction (get + delete). A second callback with the
    # same state finds nothing, so a captured callback URL cannot be replayed.
    transaction = await request.app.state.oauth_transaction_store.consume(state)
    if transaction is None:
        raise HTTPException(400, "Expired or reused OIDC callback")
    if transaction.redirect_uri != request.app.state.oidc.settings.redirect_uri:
        raise HTTPException(400, "OIDC redirect configuration changed")

    # Step 3: exchange the code for tokens and validate the ID token (signature, nonce, audience).
    # Only token/protocol rejections become 401. Network failures reaching the provider are
    # not caught here and become a 5xx: that is our outage, not a bad login.
    try:
        claims = await request.app.state.oidc.exchange(
            code=code, state=state, verifier=transaction.code_verifier, nonce=transaction.nonce
        )
    except (JoseError, OAuthError, ValueError):
        raise HTTPException(401, "Identity provider authentication failed") from None

    # Step 4: collect roles from the standard `roles` claim (Entra app roles) and
    # Keycloak's `realm_access.roles`.
    roles = set(claims.get("roles", []))
    realm = claims.get("realm_access") or {}
    if isinstance(realm, dict):
        roles.update(realm.get("roles") or [])

    # Step 5: map provider roles to GoldenGuide roles. Only explicitly configured roles count:
    # a successful institutional login alone does not prove someone is a student or an admin.
    admin = request.app.state.oidc.settings.admin_role in roles
    student_role = request.app.state.student_role
    student = bool(student_role) and student_role in roles

    # Step 6: create the server-side session. The browser only gets an opaque random ID.
    session_id = secrets.token_urlsafe(32)
    session = AuthSession(
        # Issuer-qualified so identical `sub` values from different providers never collide.
        subject=f"{request.app.state.oidc.metadata.issuer}|{claims['sub']}",
        roles=tuple(role for role, granted in (("admin", admin), ("student", student)) if granted),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=SESSION_SECONDS),
    )
    await request.app.state.session_store.create(session_id, session, SESSION_SECONDS)

    # Step 7: back to the site with the session cookie; the one-time state cookie is no longer needed.
    response = RedirectResponse(request.app.state.site_origin + "/", status_code=303)
    response.delete_cookie("gg_oidc_state", path="/")
    response.set_cookie("gg_session", session_id, max_age=SESSION_SECONDS, **_cookie_options(request))
    return response


@router.get("/me")
async def me(request: Request) -> dict:
    """Return the signed-in subject and roles, or 401."""
    _enabled(request)
    session_id = request.cookies.get("gg_session")
    session = await request.app.state.session_store.get(session_id) if session_id else None
    if session is None:
        raise HTTPException(401, "Not signed in")
    return {"subject": session.subject, "roles": list(session.roles)}


@router.post("/logout", dependencies=[Depends(require_same_origin)])
async def logout(request: Request) -> JSONResponse:
    """Revoke the session server-side and clear the cookie. Cross-origin calls are rejected (CSRF)."""
    _enabled(request)
    # Revoke in Redis first, so the cookie is useless even if the browser keeps a copy.
    session_id = request.cookies.get("gg_session")
    if session_id:
        await request.app.state.session_store.revoke(session_id)
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie("gg_session", path="/")
    return response
