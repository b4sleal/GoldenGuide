"""Authorization and production CSP tests for FastAPI's documentation UI."""
import base64
import hashlib
from html.parser import HTMLParser

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.auth import get_principal
from backend.api.docs import install_admin_docs
from backend.api.middleware.security_headers import SecurityHeadersMiddleware
from backend.domain.entities.auth.principal import Principal, Role


def _app(roles: frozenset[Role] | None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    install_admin_docs(app)
    app.add_middleware(
        SecurityHeadersMiddleware,
        production=True,
        frame_ancestors="'none'",
        additional_csp="",
    )

    async def principal():
        if roles is None:
            raise HTTPException(401, "Authentication required")
        return Principal(subject="test", roles=roles)

    app.dependency_overrides[get_principal] = principal
    return app


def test_anonymous_cannot_access_docs_or_schema():
    with TestClient(_app(None)) as client:
        docs = client.get("/docs")
        assert docs.status_code == 401
        assert "sha256-" not in docs.headers["content-security-policy"]
        assert client.get("/openapi.json").status_code == 401


def test_student_cannot_access_docs_or_schema():
    with TestClient(_app(frozenset({Role.STUDENT}))) as client:
        docs = client.get("/docs")
        assert docs.status_code == 403
        assert "sha256-" not in docs.headers["content-security-policy"]
        assert client.get("/openapi.json").status_code == 403


def test_admin_can_use_standard_swagger_and_schema():
    with TestClient(_app(frozenset({Role.ADMIN}))) as client:
        docs = client.get("/docs")
        assert docs.status_code == 200
        assert "Swagger UI" in docs.text
        assert "url: '/openapi.json'" in docs.text
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert schema.json()["openapi"].startswith("3.")


class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts: list[str] = []
        self.in_inline_script = False

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.in_inline_script = "src" not in dict(attrs)

    def handle_data(self, data):
        if self.in_inline_script:
            self.scripts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_inline_script = False


def test_production_csp_authorizes_swagger_initializer_only():
    app = _app(frozenset({Role.ADMIN}))

    @app.get("/other")
    async def other():
        return {"ok": True}

    with TestClient(app) as client:
        docs = client.get("/docs")
        assert docs.status_code == 200
        parser = InlineScripts()
        parser.feed(docs.text)
        assert parser.scripts
        script_policy = next(
            directive for directive in docs.headers["content-security-policy"].split("; ")
            if directive.startswith("script-src ")
        )
        for script in parser.scripts:
            digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
            assert f"'sha256-{digest}'" in script_policy
        assert "'self'" in script_policy
        assert "https://cdn.jsdelivr.net" in script_policy
        assert "'unsafe-inline'" not in script_policy
        assert "'unsafe-eval'" not in script_policy
        assert "object-src 'none'" in docs.headers["content-security-policy"]
        assert docs.headers["x-frame-options"] == "DENY"

        # Serving docs must not change the policy for subsequent requests.
        for path in ("/openapi.json", "/other"):
            response = client.get(path)
            assert response.status_code == 200
            assert "sha256-" not in response.headers["content-security-policy"]
