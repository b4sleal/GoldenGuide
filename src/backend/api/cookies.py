"""Browser cookies: shared flags, and the anonymous device ID that lets a browser find its own chats."""
import re
import secrets

from fastapi import Request
from starlette.responses import Response

from backend.domain.settings.service_clients import hash_key

ANONYMOUS_CLIENT_COOKIE = "gg_client"
ANONYMOUS_CLIENT_SECONDS = 31536000  # 1 year; renewed on every chat request.


def cookie_options(request: Request) -> dict:
    """Cookie flags: not readable by JS, HTTPS-only when the site is HTTPS, sent on top-level navigation."""
    return {
        "httponly": True,
        "secure": request.app.state.site_origin.startswith("https://"),
        "samesite": "lax",
        "path": "/",
    }


CLIENT_ID_BYTES = 32
_CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")  # token_urlsafe(32): 43 URL-safe characters.


def anonymous_client_id(request: Request) -> str:
    """This browser's random device ID, or a new one. Identifies a device, never a person.

    A malformed cookie is replaced rather than trusted, so clients can't choose arbitrary IDs.
    """
    existing = request.cookies.get(ANONYMOUS_CLIENT_COOKIE)
    if existing and _CLIENT_ID_PATTERN.fullmatch(existing):
        return existing
    return secrets.token_urlsafe(CLIENT_ID_BYTES)


def remember_anonymous_client(request: Request, response: Response, client_id: str) -> None:
    response.set_cookie(
        ANONYMOUS_CLIENT_COOKIE, client_id, max_age=ANONYMOUS_CLIENT_SECONDS, **cookie_options(request),
    )


def client_id_hash(client_id: str) -> str:
    """Only this hash is stored, so a database leak does not expose working device IDs."""
    return hash_key(client_id)
