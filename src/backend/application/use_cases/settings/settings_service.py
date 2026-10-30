"""Runtime settings (prompts, model choices, ...) editable by admins, layered over YAML defaults.

Read order: cache -> PostgreSQL -> YAML defaults. The YAML `version` decides precedence: raising it in
ai_behavior.yml replaces stored settings on next read; an equal or newer stored version keeps admin
edits and only fills in fields the YAML added since. Saves never change the version.
"""
import json

import structlog

from backend.domain.ports.repositories.app.app_db import AppDB
from backend.domain.settings.ai_behavior import RuntimeDefaultsCatalog
from backend.shared.utils.deep_merge import deep_merge_dicts

from .settings_cache import SettingsCacheService

logger = structlog.get_logger()


class SettingsService:
    DB_KEY = "system_config"

    def __init__(
            self,
            app_db: AppDB,
            cache: SettingsCacheService,
            runtime_defaults: RuntimeDefaultsCatalog,
    ):
        self.db = app_db
        self.cache = cache
        self.runtime_defaults = runtime_defaults

    async def get(self) -> RuntimeDefaultsCatalog:
        """The current settings: saved customizations merged over the YAML defaults."""
        defaults = self.runtime_defaults
        yaml_version = defaults.version

        # 1. Redis: use only settings matching or exceeding YAML version.
        cached = await self.cache.get()

        if cached is not None:
            cached_version = int(cached.get("version", 0))

            if cached_version >= yaml_version:
                settings = RuntimeDefaultsCatalog.model_validate(
                    deep_merge_dicts(defaults.model_dump(), cached)
                )
                return settings

            logger.info(
                "settings_cache_outdated",
                cached_version=cached_version,
                yaml_version=yaml_version,
            )

        # 2. PostgreSQL: persistent source of truth.
        async with self.db.start() as repos:
            raw = await repos.settings.get(self.DB_KEY)

        if raw is None:
            logger.info(
                "settings_initialized_from_yaml",
                version=yaml_version,
            )
            await self._persist(defaults)
            return defaults

        stored = json.loads(raw)
        stored_version = int(stored.get("version", 0))

        # 3. A newer YAML version replaces stored settings completely.
        if yaml_version > stored_version:
            logger.info(
                "settings_yaml_version_upgrade",
                old_version=stored_version,
                new_version=yaml_version,
            )

            await self._persist(defaults)
            return defaults

        # 4. Same/newer stored version: preserve saved customizations,
        # while filling in any newly introduced model fields.
        merged = deep_merge_dicts(
            defaults.model_dump(),
            stored,
        )

        settings = RuntimeDefaultsCatalog.model_validate(merged)

        if merged != stored:
            logger.info(
                "settings_schema_migrated",
                version=settings.version,
            )
            await self._persist(settings)
        else:
            await self.cache.set(settings.model_dump())

        return settings

    async def save(self, updates: dict) -> RuntimeDefaultsCatalog:
        """
        Apply user edits without changing the YAML configuration version.

        Version is reserved for YAML-controlled configuration upgrades.
        """
        if "version" in updates:
            raise ValueError(
                "Settings version is managed by ai_behavior.yml"
            )

        current = await self.get()

        new_data = deep_merge_dicts(
            current.model_dump(),
            updates,
        )

        new_data["version"] = current.version

        updated = RuntimeDefaultsCatalog.model_validate(new_data)

        await self._persist(updated)

        logger.info(
            "settings_updated",
            version=updated.version,
        )

        return updated

    async def _persist(
            self,
            settings: RuntimeDefaultsCatalog,
    ) -> None:
        # Persist to PostgreSQL first.
        async with self.db.start() as repos:
            await repos.settings.save(
                key=self.DB_KEY,
                value=settings.model_dump_json(),
            )

        # Refresh the cache after the commit. A cache failure is logged by the cache service and does
        # not undo or fail the committed save.
        await self.cache.set(settings.model_dump())
