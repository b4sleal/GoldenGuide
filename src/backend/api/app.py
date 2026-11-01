"""Build the FastAPI application: validate HTTP settings, install middleware, register routes.

Dependency wiring (DI container, stores, instrumentation) happens in factory.py, so tests can
call create_app() with a fake SecretReader and no running infrastructure.
"""
from ipaddress import ip_network

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api.docs import install_admin_docs
from backend.api.errors import install_error_handlers
from backend.api.middleware.error_boundary import ErrorBoundaryMiddleware
from backend.api.middleware.http_only import HttpOnlyMiddleware
from backend.api.middleware.request_context import RequestContextMiddleware
from backend.api.middleware.security_headers import SecurityHeadersMiddleware
from backend.api.routes import router
from backend.api.routes.chat import CONVERSATION_HEADER
from backend.api.routes.identity import router as identity_router
from backend.api.spa import FRONTEND_BUILD_DIR, SpaStaticFiles
from goldenguide_common.config.secret_reader import SecretReader


def csv_setting(reader: SecretReader, name: str, default: str) -> list[str]:
    """Read a comma-separated setting as a list, ignoring blank entries."""
    return [part.strip() for part in reader.get(name, default).split(",") if part.strip()]


def positive_int_setting(reader: SecretReader, name: str, default: int) -> int:
    """Read a positive integer setting; a bad value fails startup instead of a later request."""
    raw = reader.get(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def create_app(reader: SecretReader) -> FastAPI:
    # ---- Step 1: read and validate core HTTP settings (fail fast at boot) ----
    production = reader.get("APP_ENV", "development").lower() == "production"
    mode = reader.get("AUTH_MODE", "disabled")
    origin = reader.get("SITE_ORIGIN", "http://localhost:8080").rstrip("/")

    # Development convenience: admin access without sign-in, for this machine only (see auth.py).
    local_admin = reader.get("LOCAL_ADMIN", "false").lower() == "true"

    if mode not in {"disabled", "oidc"}:
        raise ValueError("AUTH_MODE must be disabled or oidc")
    if production and not origin.startswith("https://"):
        raise ValueError("SITE_ORIGIN must use HTTPS in production")
    if production and local_admin:
        raise ValueError("LOCAL_ADMIN cannot be enabled in production")

    # ---- Step 2: create the app with FastAPI's public docs disabled (docs.py serves admin-only copies) ----
    app = FastAPI(
        title="GoldenGuide API",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # ---- Step 3: request-independent state read by routes and dependencies ----
    app.state.auth_mode = mode
    app.state.local_admin = local_admin
    app.state.site_origin = origin
    app.state.secret_reader = reader
    app.state.student_role = reader.get("OIDC_STUDENT_ROLE", "")
    app.state.oidc = None
    # Bearer-key callers; none until factory.py attaches the configured ones, so bearer auth fails closed.
    app.state.service_clients = {}
    # Public chat limit per client IP; defaults keep the previous 10 requests / 60 s.
    app.state.chat_rate_limit = positive_int_setting(reader, "CHAT_RATE_LIMIT", 20)
    app.state.chat_rate_window_seconds = positive_int_setting(reader, "CHAT_RATE_WINDOW_SECONDS", 60)

    # ---- Step 4: OIDC sign-in (only when enabled) ----
    if mode == "oidc":
        required = ("OIDC_DISCOVERY_URL", "OIDC_CLIENT_ID", "OIDC_REDIRECT_URI", "OIDC_ADMIN_ROLE")
        missing = [key for key in required if not reader.get(key)]
        if missing:
            raise ValueError(f"Missing OIDC settings: {', '.join(missing)}")

        # The callback must land on the same origin that set the state cookie,
        # otherwise the browser will not send that cookie and every login fails.
        redirect = reader.get("OIDC_REDIRECT_URI", "")
        if redirect != f"{origin}/api/v1/auth/callback":
            raise ValueError("OIDC_REDIRECT_URI must match SITE_ORIGIN + /api/v1/auth/callback")

    # Proxies whose forwarded client-IP headers we trust (rate limiting). Invalid CIDRs raise at boot.
    app.state.trusted_proxy_networks = [
        ip_network(value.strip())
        for value in reader.get("TRUSTED_PROXY_CIDRS", "").split(",")
        if value.strip()
    ]

    # ---- Step 5: handlers for expected errors (HTTPException, validation, domain errors) ----
    install_error_handlers(app)

    # ---- Step 6: middleware ----
    # add_middleware() wraps the app, so the LAST one added is the OUTERMOST. Request flow:
    #
    #   HttpOnly -> CORS -> SecurityHeaders -> RequestContext -> ErrorBoundary -> TrustedHost -> routes
    #
    # Why this order:
    #   - HttpOnly first: the API has no WebSocket endpoints, so those handshakes are refused here.
    #   - CORS outermost: every response, including errors, gets CORS headers, so the browser
    #     lets the frontend read our error JSON instead of reporting a network failure.
    #   - SecurityHeaders next: every response, including errors, gets CSP/nosniff/etc.
    #   - RequestContext before ErrorBoundary: the request ID exists before any error is built,
    #     and the access log records the final status (including 500s).
    #   - TrustedHost inside the boundary: rejected hosts still get a request ID.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=csv_setting(
            reader,
            "ALLOWED_HOSTS",
            "localhost,127.0.0.1,backend,askgoldenguide.ca,www.askgoldenguide.ca",
        ),
    )
    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        SecurityHeadersMiddleware,
        production=production,
        frame_ancestors=reader.get("FRAME_ANCESTORS", "'none'"),
        additional_csp=reader.get("CSP_ADDITIONAL_SOURCES", ""),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=csv_setting(
            reader,
            "CORS_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080,"
            "https://askgoldenguide.ca,https://www.askgoldenguide.ca",
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        # Let cross-origin frontends (e.g. an embedded widget) read the ID for bug reports.
        expose_headers=["X-Request-ID", CONVERSATION_HEADER],
    )
    # Outermost of all: turn away WebSocket handshakes before any HTTP-only component sees them.
    app.add_middleware(HttpOnlyMiddleware)

    # ---- Step 7: health endpoints ----
    # Liveness only: "the process answers HTTP". It deliberately does not check Postgres/Redis/
    # Qdrant; a dependency outage should not make the orchestrator restart a healthy process.
    # A dependency-aware readiness endpoint is a separate, upcoming change.
    @app.get("/health/live", tags=["Health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    # Same check under the old path; docker-compose.yml's healthcheck still calls /health.
    @app.get("/health", include_in_schema=False)
    async def legacy_health() -> dict[str, str]:
        return {"status": "ok"}

    # ---- Step 8: API routes ----
    app.include_router(identity_router, prefix="/api/v1")
    app.include_router(router, prefix="/api/v1")

    # Protected documentation must be registered before the catch-all frontend mount below.
    install_admin_docs(app)

    # ---- Step 9: static frontend (last, because "/" matches everything not matched above) ----
    if reader.get("SERVE_FRONTEND", "true").lower() == "true":
        app.mount("/", SpaStaticFiles(FRONTEND_BUILD_DIR), name="frontend")

    return app
