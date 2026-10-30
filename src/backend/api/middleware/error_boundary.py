"""Turn exceptions that no handler caught into a 500 JSON response, logged exactly once.

This sits *inside* RequestContext/SecurityHeaders/CORS middleware (see app.py), so the
500 response still carries X-Request-ID, the security headers and CORS headers. Without
CORS headers a browser hides the response body, and the frontend would only see a vague
"network error" instead of our structured message.
"""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.api.errors import classify, error_body, report, request_id_of


class ErrorBoundaryMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Only HTTP requests produce error responses; lifespan/websocket pass straight through.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Track whether the status line was already sent. After that, the status cannot be changed.
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:  # Exception, not BaseException: cancellation must keep propagating.
            # Step 1: decide what the client sees (normally the generic 500).
            public = classify(exc)
            # Step 2: log the traceback + mark the trace span failed (the only place this happens).
            report(exc, public)

            # Step 3a: response already in progress (a stream). We cannot send a new status.
            # Returning here closes the connection; the frontend treats a stream without its
            # final "ok" event as interrupted. Streams normally convert their own failures into
            # an error event (api/streaming.py), so reaching this branch indicates a bug there.
            if response_started:
                return

            # Step 3b: nothing sent yet, so send the standard error envelope.
            # The exception is NOT re-raised: it has been reported, and re-raising would make
            # uvicorn print the same traceback again.
            response = JSONResponse(error_body(public, request_id_of(scope)), status_code=public.status)
            await response(scope, receive, send)
