"""Text splitter backed by LangChain's RecursiveCharacterTextSplitter (separators tried in order)."""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.domain.settings.providers import ChunkingSettings


class RecursiveTextSplitter:
    def __init__(self, chunking_profile: ChunkingSettings):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunking_profile.chunk_size,
            chunk_overlap=chunking_profile.chunk_overlap,
            separators=[*chunking_profile.separators]
        )

    def split(self, text: str) -> list[str]:
        return self.text_splitter.split_text(text)