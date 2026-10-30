"""Unit of work spanning app and school repositories in one transaction (same database only)."""
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from backend.domain.ports.repositories.app.app_db import AppRepositories
from backend.domain.ports.repositories.school.school_db import SchoolRepositories


@dataclass(frozen=True)
class PrimaryUOWRepositories:
    app: AppRepositories
    school: SchoolRepositories


class PrimaryUnitOfWork(Protocol):
    def start(self) -> AbstractAsyncContextManager[PrimaryUOWRepositories]:
        ...