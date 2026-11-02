
"""FastAPI documentation: the Swagger UI is for administrators; the schema also for `docs:read` clients."""

import base64
import hashlib
import re

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from backend.api.auth import require_admin, require_scope
from backend.domain.entities.auth.principal import Scope


def install_admin_docs(app: FastAPI) -> None:
    @app.get(
        "/docs",
        include_in_schema=False,
        response_class=HTMLResponse,
        dependencies=[Depends(require_admin)],
    )
    async def swagger_ui(request: Request):
        response = get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=f"{app.title} - Swagger UI",
            swagger_ui_parameters={
                "deepLinking": True,
                "displayRequestDuration": True,
                "filter": True,
                "persistAuthorization": False,
            },
        )
        # FastAPI emits an inline initializer. Authorize its exact bytes on this
        # response without allowing arbitrary inline scripts in production.
        scripts = re.findall(r"<script>(.*?)</script>", response.body.decode("utf-8"), flags=re.DOTALL)
        request.state.csp_script_hashes = tuple(
            "sha256-" + base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
            for script in scripts
        )
        return response

    @app.get(
        "/openapi.json",
        include_in_schema=False,
        response_class=JSONResponse,
        # Reading the schema grants no route: each route still checks its own scope.
        dependencies=[Depends(require_scope(Scope.DOCS_READ))],
    )
    async def openapi_schema():
        return JSONResponse(app.openapi())
