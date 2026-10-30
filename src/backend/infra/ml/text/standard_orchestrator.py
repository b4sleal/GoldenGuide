"""Text splitter orchestrator: route to the splitter named by the collection's chunking settings."""
from collections.abc import Mapping

from backend.domain.ports.providers.text_splitter import TextSplitter
from backend.domain.settings.providers import ChunkingSettings


class StandardTextSplitterOrchestrator:
    def __init__(self, text_splitter_providers: Mapping[str, TextSplitter]):
        self.text_splitter_providers = text_splitter_providers

    def split(self, text: str, chunking_profile: ChunkingSettings) -> list[str]:
        return self.text_splitter_providers[chunking_profile.name].split(text)