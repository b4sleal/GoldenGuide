"""The single place where exceptions become client-visible errors.

Everything that reports an error to a client goes through `classify()`:
    - HTTP handlers registered below (expected errors: 4xx, domain errors).
    - ErrorBoundaryMiddleware (unexpected errors -> 500).
    - The chat stream's `error` event (api/streaming.py).
So one exception always produces the same status, code and message, whichever path it takes.

Every error response has the same JSON envelope:
    {"error": {"code": ..., "message": ..., "request_id": ..., "trace_id": ...}}
`request_id` matches the X-Request-ID header and the logs; `trace_id` opens the trace in Jaeger.
"""
from dataclasses import dataclass

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from backend.domain.errors import (
    INTERNAL_ERROR_CODE,
    ConflictError,
    DeadlineExceededError,
    DependencyUnavailableError,
    GoldenGuideError,
    InvalidInputError,
    NotFoundError,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PublicError:
    """What the client is allowed to see about a failure."""

    status: int
    code: str
    message: str


# Domain error category -> HTTP status. The public code is the error's own (domain/errors.py).
# Subclasses inherit their parent's mapping (see the MRO walk in classify()).
_DOMAIN_STATUS: dict[type[GoldenGuideError], int] = {
    InvalidInputError: 422,
    NotFoundError: 404,
    ConflictError: 409,
    DependencyUnavailableError: 503,
    DeadlineExceededError: 504,
}

# HTTPException status -> stable public code. The frontend can switch on `code`
# instead of parsing human-readable messages.
_HTTP_CODES: dict[int, str] = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "invalid_input",
    429: "rate_limited",
    501: "not_implemented",
    503: "service_unavailable",
}

# Anything we did not anticipate. Never expose str(exc) for these: it can contain internals.
INTERNAL_ERROR = PublicError(500, INTERNAL_ERROR_CODE, "Internal server error")


def classify(exc: Exception) -> PublicError:
    """Map any exception to the status/code/message the client should see."""
    # 1. Errors raised deliberately by API code (auth, rate limit, upload size, ...).
    #    Their detail strings are written by us for clients, so they are safe to return.
    if isinstance(exc, StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return PublicError(exc.status_code, code, str(exc.detail))

    # 2. FastAPI request-body/query validation. Never echo the input back: it can contain student data.
    if isinstance(exc, RequestValidationError):
        return PublicError(422, "invalid_input", "Request validation failed")

    # 3. Domain errors. Walk the class hierarchy so subclasses use their parent's mapping.
    if isinstance(exc, GoldenGuideError):
        for cls in type(exc).__mro__:
            if cls in _DOMAIN_STATUS:
                return PublicError(_DOMAIN_STATUS[cls], exc.code, exc.public_message)

    # 4. Everything else is a bug or an unclassified infrastructure failure.
    return INTERNAL_ERROR


def report(exc: Exception, public: PublicError) -> None:
    """Log and trace a failure once, at the boundary that turned it into a response."""
    # 4xx means the client did something wrong; the access log (request_context.py)
    # already records the status, so a second log line would only be noise.
    if public.status < 500:
        return

    # 5xx means we failed. Attach the exception to the active span so the trace shows it...
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, public.code))

    # ...and log the full traceback exactly once. request_id is already bound by
    # RequestContextMiddleware, so this line can be joined with the access log.
    logger.error(
        "request.failed",
        exc_info=exc,
        error_type=type(exc).__name__,
        error_code=public.code,
        status_code=public.status,
    )


def request_id_of(scope: Scope) -> str | None:
    """Read the ID RequestContextMiddleware stored for this request (None if it never ran)."""
    return scope.get("state", {}).get("request_id")


def current_trace_id() -> str | None:
    """The active trace's ID in the 32-hex-digit form Jaeger/Grafana search expects (None if untraced)."""
    ctx = trace.get_current_span().get_span_context()
    return f"{ctx.trace_id:032x}" if ctx.is_valid else None


def error_body(public: PublicError, request_id: str | None) -> dict:
    """Build the standard error envelope shared by JSON responses and stream error events."""
    return {
        "error": {
            "code": public.code,
            "message": public.message,
            "request_id": request_id,
            "trace_id": current_trace_id(),
        }
    }


async def _handle_expected(request: Request, exc: Exception) -> JSONResponse:
    """Shared handler for every exception type registered in install_error_handlers()."""
    public = classify(exc)
    report(exc, public)
    response = JSONResponse(error_body(public, request_id_of(request.scope)), status_code=public.status)

    # Keep headers the raiser attached on purpose, e.g. Retry-After on 429.
    if isinstance(exc, StarletteHTTPException) and exc.headers:
        response.headers.update(exc.headers)
    return response


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers for errors we anticipate.

    Unexpected exceptions are NOT registered here on purpose. A handler for `Exception`
    runs in Starlette's outermost ServerErrorMiddleware, which (a) sends the response
    without CORS/security/request-ID headers and (b) re-raises, so uvicorn logs the
    traceback a second time. ErrorBoundaryMiddleware handles them instead.
    """
    app.add_exception_handler(StarletteHTTPException, _handle_expected)
    app.add_exception_handler(RequestValidationError, _handle_expected)
    app.add_exception_handler(GoldenGuideError, _handle_expected)
