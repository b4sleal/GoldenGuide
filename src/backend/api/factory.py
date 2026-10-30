"""ASGI composition: build the DI container, create the app, attach stores, instrument."""
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from backend.api.app import create_app
from backend.core.startup.runtime import build_container, lifespan
from backend.domain.settings.oidc import OIDCSettings
from backend.infra.security.oidc.authlib_client import AuthlibOIDCClient


def build_app():
    # Step 1: build the dependency-injection container (loads config, starts telemetry).
    container = build_container()

    # Step 2: create the HTTP app from the same configuration source.
    app = create_app(reader=container.secret_reader())
    app.container = container

    # Step 3: attach the Redis-backed stores that dependencies read from app.state.
    # Session/OAuth stores only exist when sign-in is enabled; auth.py fails closed otherwise.
    oidc_enabled = app.state.auth_mode == "oidc"
    if oidc_enabled:
        # Credentials come from SecretReader; verification policy comes from the merged YAML.
        # Keep provider construction here so the HTTP app does not own adapter configuration.
        app.state.oidc = AuthlibOIDCClient(
            settings=OIDCSettings(
                discovery_url=app.state.secret_reader.get("OIDC_DISCOVERY_URL", ""),
                client_id=app.state.secret_reader.get("OIDC_CLIENT_ID", ""),
                client_secret=app.state.secret_reader.get("OIDC_CLIENT_SECRET", ""),
                redirect_uri=app.state.secret_reader.get("OIDC_REDIRECT_URI", ""),
                admin_role=app.state.secret_reader.get("OIDC_ADMIN_ROLE", ""),
            ),
            policy=container.app_config().system.oidc,
        )
    app.state.session_store = container.persistence.session_store() if oidc_enabled else None
    app.state.oauth_transaction_store = container.persistence.oauth_transaction_store() if oidc_enabled else None
    app.state.rate_limit_store = container.persistence.rate_limit_store()
    # Service clients without key hashes are left out, so a client is enabled only by setting its secret.
    app.state.service_clients = {
        name: client for name, client in container.app_config().system.service_clients.items() if client.key_hashes
    }

    # Step 4: startup/shutdown hooks (DB init, vector collections, OIDC discovery, telemetry flush).
    app.router.lifespan_context = lifespan

    # Step 5: let @inject / Provide[...] in route modules resolve from this container.
    container.wire(packages=["backend.api"])

    # Step 6: one trace span per request; health/docs are excluded because they are noise.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/health,/health/live,/docs,/openapi.json")
    return app
