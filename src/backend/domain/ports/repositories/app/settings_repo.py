"""Settings repository port: versioned runtime settings documents by key."""
from typing import Protocol


class SettingsRepository(Protocol):
    async def get(self, key: str) -> str | None:
        ...

    async def save(self, key: str, value) -> None:
        ...