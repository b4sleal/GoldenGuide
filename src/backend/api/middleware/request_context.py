"""Give every HTTP request an ID and write one access-log line when it finishes.

The ID is:
    - stored in scope["state"] so error responses can include it (api/errors.py),
    - bound into structlog context so every log line during the request carries it,
    - returned to the client as the X-Request-ID header so a user report can be traced.
This middleware never handles exceptions; ErrorBoundaryMiddleware (inside it) does.
"""
import time
from uuid import uuid4

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.get_logger(__name__)

# Liveness endpoints polled by Docker / load balancers (see app.py, docker-compose.yml).
_PROBE_PATHS = frozenset({"/health", "/health/live"})


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Step 1: create the ID. Generated server-side: a client-supplied ID could be forged
        # to pollute or collide with other requests' logs.
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        # Step 2: start a clean logging context for this request.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        # Stays 500 only if no response was ever started (should not happen: the error
        # boundary always sends one), so the access log never under-reports a failure.
        status = 500

        # Step 3: capture the status and add the X-Request-ID header on the way out.
        async def tracked_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        finally:
            # Step 4: one access log per request. For streams this fires when the stream
            # ends, so duration_ms covers the whole answer, not just time to first byte.
            # Successful health probes (Docker / load balancer, every few seconds) are skipped:
            # they would bury real traffic. A failing probe is still logged.
            if not (scope["path"] in _PROBE_PATHS and status < 400):
                logger.info(
                    "http.completed",
                    method=scope["method"],
                    path=scope["path"],
                    status_code=status,
                    duration_ms=round((time.perf_counter() - start) * 1000, 2),
                )
            structlog.contextvars.clear_contextvars()
