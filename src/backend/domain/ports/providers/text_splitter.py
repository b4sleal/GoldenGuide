"""Text splitter port: split text into chunks per the collection's chunking settings."""
from typing import Protocol

from backend.domain.settings.providers import ChunkingSettings


class TextSplitter(Protocol):
    def split(self, text: str) -> list[str]: pass


class TextSplitterOrchestrator(Protocol):
    def split(self, text: str, chunking_profile: ChunkingSettings) -> list[str]: ...
