"""Application database port: one unit of work exposing the app repositories."""
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio.session import AsyncSession

from backend.domain.ports.repositories.app.conversation_repo import ConversationRepository
from backend.domain.ports.repositories.app.document_repo import DocumentRepository
from backend.domain.ports.repositories.app.job_repo import JobRepository
from backend.domain.ports.repositories.app.settings_repo import SettingsRepository


@dataclass(frozen=True,slots=True)
class AppRepositories:
    documents: DocumentRepository
    settings: SettingsRepository
    jobs: JobRepository
    conversations: ConversationRepository


class AppDB(Protocol):
    def start(
            self,
            session: AsyncSession | None = None,
    ) -> AbstractAsyncContextManager[AppRepositories]:
        ...