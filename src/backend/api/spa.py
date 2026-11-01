"""Serve the built single-page frontend (frontend/dist) when FastAPI runs without the Nginx container.

Client-side routes such as /c/<conversation-id> exist only in the browser, so a request for one
(a reload or a shared link) is answered with index.html and the frontend's router takes over.
"""
from pathlib import Path, PurePath

from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

FRONTEND_BUILD_DIR = Path("frontend/dist")
INDEX_FILE = "index.html"
# Unknown API paths keep their JSON 404 instead of receiving the app's HTML.
API_SEGMENT = "api"


class SpaStaticFiles(StaticFiles):
    def __init__(self, directory: Path):
        if not (directory / INDEX_FILE).is_file():
            raise RuntimeError(
                f"Frontend build not found at {directory}: run `pnpm build` in frontend/ or set SERVE_FRONTEND=false"
            )
        super().__init__(directory=directory, html=True)

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # StaticFiles hands over an OS-native path ("api\\v1\\x" on Windows), so compare path parts.
            # Only extensionless paths are app routes; a missing asset (.js, .png) stays a real 404.
            parts = PurePath(path)
            if exc.status_code != 404 or parts.parts[:1] == (API_SEGMENT,) or parts.suffix:
                raise
            return await super().get_response(INDEX_FILE, scope)
