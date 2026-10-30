"""Per-client rate limit for public chat endpoints.

The counter lives in the shared rate-limit store (Redis), so the limit holds across
every API replica. This module only decides *who* the client is and *what* the policy is.
"""
from ipaddress import ip_address

from fastapi import HTTPException, Request


def _client_address(request: Request) -> str:
    """Identify the caller, trusting forwarded headers only from configured proxies."""
    # Step 1: the TCP peer. Behind Cloudflare/NGINX this is the proxy, not the student.
    remote = request.client.host if request.client else None
    if remote is None:
        # No peer address (unusual test/ASGI setups). Such callers share one bucket.
        return "unknown"

    # Step 2: only believe the forwarded IP when the peer is one of our proxies
    # (TRUSTED_PROXY_CIDRS). Anyone else could put any value in that header.
    try:
        peer_is_trusted_proxy = any(
            ip_address(remote) in network for network in request.app.state.trusted_proxy_networks
        )
    except ValueError:
        # Peer is not an IP (e.g. a unix socket name): it cannot be a trusted proxy.
        peer_is_trusted_proxy = False

    if not peer_is_trusted_proxy:
        return remote

    # Step 3: Cloudflare puts the original client IP in CF-Connecting-IP.
    claimed = request.headers.get("cf-connecting-ip")
    if not claimed:
        return remote
    try:
        # Normalize so "::ffff:1.2.3.4"-style variants cannot create separate buckets.
        return str(ip_address(claimed))
    except ValueError:
        raise HTTPException(400, "Invalid client address") from None


async def limit_chat(request: Request) -> None:
    """Consume one request from the caller's window, or reject with 429 + Retry-After."""
    state = request.app.state
    # If the store is unreachable this raises and the request fails with a 5xx (fail closed):
    # an outage of the limiter must not turn into unlimited paid LLM calls.
    result = await state.rate_limit_store.consume(
        _client_address(request),
        limit=state.chat_rate_limit,
        window_seconds=state.chat_rate_window_seconds,
    )
    if not result.allowed:
        raise HTTPException(
            429,
            "Too many requests",
            headers={"Retry-After": str(max(1, result.retry_after_seconds))},
        )
