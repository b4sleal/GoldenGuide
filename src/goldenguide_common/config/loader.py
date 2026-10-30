"""Load the YAML configuration tree, fill in secrets, and validate it into typed settings.

Directory layout under CONFIG_PATH (default: ./configs), merged in this order (later wins):

    base/*.yml               defaults shared by every environment
    catalogs/<group>/*.yml   what exists (providers, profiles) and what is active
    environments/<APP_ENV>.yml   development / staging / production overrides

Secrets are never written in YAML. A value like `${secrets:DB__POSTGRES__PASSWORD}` is looked up
through the SecretReader (environment variables today; a secrets manager later).
"""
from pathlib import Path
from typing import Any

from omegaconf import OmegaConf

from backend.domain.settings.app_config import AppConfig
from embedding_service.settings import LocalEmbeddingServiceConfig
from goldenguide_common.config.secret_reader import SecretReader


class ConfigLoader:
    # Catalog groups whose entries get a `name` field equal to their YAML key (see load_resolved).
    NAMED_CONFIG = "catalog"
    NAMED_CONFIG_PROFILES = ["active", "profiles", "providers"]
    NAMED_CONFIG_ITEM_KEY = "name"

    def __init__(self, secret_reader: SecretReader):
        self.secret_reader = secret_reader
        self.app_env = secret_reader.get("APP_ENV", "development")

        # Resolve every directory up front and fail at boot with a clear message if any is missing.
        self.config_root = Path(secret_reader.get("CONFIG_PATH", "configs")).resolve()
        self.base_dir = self.config_root / "base"
        self.catalog_dir = self.config_root / "catalogs"
        self.env_overrides = self.config_root / "environments" / f"{self.app_env}.yml"

        for path, label in (
            (self.config_root, "Config root directory"),
            (self.base_dir, "Base config directory"),
            (self.catalog_dir, "Catalog config directory"),
            (self.env_overrides, f"Environment overrides file for APP_ENV={self.app_env!r}"),
        ):
            if not path.exists():
                raise FileNotFoundError(f"{label} not found: {path}")

    def load_all_yaml(self) -> Any:
        """Merge every YAML file in precedence order. Sorted so the merge order never depends on the OS."""
        configs = []

        # 1. Base defaults.
        for file in sorted(self.base_dir.glob("*.yml")):
            configs.append(OmegaConf.load(file))

        # 2. Catalogs, one subdirectory per group.
        for inner_dir in sorted(self.catalog_dir.iterdir()):
            if inner_dir.is_dir():
                for file in sorted(inner_dir.glob("*.yml")):
                    configs.append(OmegaConf.load(file))

        # 3. Environment overrides, last so they win.
        configs.append(OmegaConf.load(self.env_overrides))

        return OmegaConf.merge(*configs)

    def load_resolved(self) -> dict:
        """Merge YAML, inject catalog item names, resolve ${...} references into a plain dict."""
        cfg = self.load_all_yaml()

        # `${secrets:KEY}` -> SecretReader lookup. replace=True because OmegaConf resolvers are global
        # and a process may create more than one loader.
        OmegaConf.register_new_resolver(
            "secrets", lambda key, default=None: self.secret_reader.get(key, default), replace=True,
        )

        # Copy each catalog item's key into a `name` field, e.g.
        #   profiles: { deep_cloud: {...} }  ->  profiles: { deep_cloud: { name: "deep_cloud", ... } }
        # Some objects (like an LLM profile) are passed around without their key, and logs and
        # fallbacks need to know which entry they came from.
        for catalog_group, group_values in cfg[self.NAMED_CONFIG].items():
            if catalog_group in self.NAMED_CONFIG_PROFILES:
                for catalog in group_values.values():
                    for name, item in catalog.items():
                        item[self.NAMED_CONFIG_ITEM_KEY] = name

        return OmegaConf.to_container(cfg, resolve=True)

    def load_app_config(self) -> AppConfig:
        """Full, validated configuration for the API backend."""
        return AppConfig.model_validate(self.load_resolved())

    def load_local_embedding_config(self) -> LocalEmbeddingServiceConfig:
        """The subset of configuration the embedding service needs.

        Note: this still validates the whole AppConfig, so the embedding service needs the full
        config tree. Splitting shared contracts into their own package is a planned cleanup.
        """
        resolved = self.load_app_config()
        return LocalEmbeddingServiceConfig(
            settings=resolved.local_embedding_service,
            local_sparse_vectorizer=resolved.catalog.providers.local_sparse_vectorizer,
            local_embedding=resolved.catalog.providers.local_embedding,
            local_reranker=resolved.catalog.providers.local_reranker,
        )
