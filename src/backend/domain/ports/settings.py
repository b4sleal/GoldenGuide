"""Read-only runtime settings port."""
from typing import Protocol

from backend.domain.settings.ai_behavior import RuntimeDefaultsCatalog


class RuntimeSettingsReader(Protocol):
    """Read access to the admin-editable runtime settings (prompts, generation behavior)."""

    async def get(self) -> RuntimeDefaultsCatalog:
        """The current settings: saved customizations merged over the YAML defaults."""
        ...
