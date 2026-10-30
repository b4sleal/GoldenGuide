"""Refuse WebSocket connections cleanly; GoldenGuide's API is HTTP-only.

Without this, a stray WebSocket (browser extensions and IDE live-reload tools try them) falls
through the router to the static frontend mount, and Starlette's StaticFiles crashes with an
AssertionError traceback. Here it is closed before the app sees it, which a client receives as
HTTP 403, with nothing logged as an error.
"""
from starlette.types import ASGIApp, Receive, Scope, Send


class HttpOnlyMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            # Closing before accepting is the ASGI way to reject a handshake.
            await send({"type": "websocket.close", "code": 1008})  # 1008 = policy violation
            return
        await self.app(scope, receive, send)
