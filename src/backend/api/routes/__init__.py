"""Assemble the public and administrative HTTP endpoints under /api/v1."""
from fastapi import APIRouter, Depends

from backend.api.auth import get_principal, require_same_origin
from backend.api.routes import chat, documents, ingestion, jobs, scraping, settings

# Public endpoints. Chat is anonymous for now.
# Open decision: switch chat to require_student before institutional launch so WLU data
# is only served to authenticated students, if WLU requires that.
router = APIRouter()
router.include_router(chat.router, prefix="/chat", tags=["Chat"])

# Administrative endpoints: every route below requires an authenticated caller, and every
# state-changing request (POST/PATCH/DELETE) from a browser session must come from our own site origin.
# Each child router declares the scope it needs (require_scope): administrators hold every scope,
# service clients only those configured for them. Declared on the child, it stays protected even if it
# is ever mounted somewhere else. FastAPI caches dependencies per request, so get_principal runs once.
admin = APIRouter(prefix="/admin", dependencies=[Depends(get_principal), Depends(require_same_origin)])
admin.include_router(settings.router, prefix="/settings", tags=["Settings"])
admin.include_router(documents.router, prefix="/documents", tags=["Documents"])
admin.include_router(scraping.router, prefix="/sources", tags=["Source collection"])
admin.include_router(ingestion.router, prefix="/indexing", tags=["Indexing"])
admin.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
router.include_router(admin)
