"""SecretReader backed by environment variables (plus a local .env file for development)."""
import os
from collections.abc import Mapping

from dotenv import load_dotenv

# Local development convenience: load ./.env into os.environ once, at import.
# Variables already set (e.g. by docker-compose `environment:`) are NOT overridden,
# so container and production settings always take precedence over the file.
load_dotenv()


class EnvSecretReader:
    def __init__(self, env: Mapping[str, str] | None = None):
        # Snapshot the environment once, so values cannot change mid-run.
        # Tests can pass their own mapping instead of touching os.environ.
        self._env = dict(env if env is not None else os.environ)

    def get(self, key: str, default: str | None = None) -> str | None:
        # An empty value counts as unset (`FOO=` in .env), so it falls back to the default.
        return self._env.get(key) or default
