"""The authenticated caller of a request and the roles and scopes that decide what it may do."""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Role(StrEnum):
    STUDENT = "student"
    ADMIN = "admin"


class Scope(StrEnum):
    """One administrative capability. Service clients are granted scopes; admins hold all of them."""
    SOURCES_COLLECT = "sources:collect"      # Discover and import Academic Calendar, website and LORIS data.
    INDEXING_SYNC = "indexing:sync"          # Embed records into the vector store.
    JOBS_READ = "jobs:read"                  # Read the status and outcome of job runs.
    SETTINGS_WRITE = "settings:write"        # Read and change runtime settings (prompts, models).
    DOCUMENTS_WRITE = "documents:write"      # List and upload documents.


class Principal(BaseModel):
    model_config = ConfigDict(frozen=True)

    subject: str
    roles: frozenset[Role]
    # Granted directly to service clients; people get their capabilities from roles instead.
    scopes: frozenset[Scope] = frozenset()

    def has_scope(self, scope: Scope) -> bool:
        return Role.ADMIN in self.roles or scope in self.scopes
