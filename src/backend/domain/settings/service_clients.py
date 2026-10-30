"""Machine callers (e.g. a scheduled GitHub Actions workflow) that authenticate with a bearer key.

Each client is configured in YAML (system.service_clients) with the scopes it may use. Only SHA-256
hashes of its keys are configured, from secrets; the key itself lives with the caller. Two hashes allow
rotation: add the new key's hash, switch the caller over, then remove the old one.
"""
import hashlib
import hmac
import re

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from backend.domain.entities.auth.principal import Scope

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def hash_key(key: str) -> str:
    """The hex SHA-256 configured for a key. Keys are long random tokens, so no salt or stretching is needed."""
    return hashlib.sha256(key.encode()).hexdigest()


class ServiceClientSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    scopes: frozenset[Scope]
    # Unset secrets resolve to empty entries; they are dropped, and a client without hashes is disabled.
    key_hashes: tuple[SecretStr, ...] = Field(default=(), max_length=2)

    @field_validator("key_hashes", mode="before")
    @classmethod
    def drop_unset_and_validate(cls, values: list[str | None] | None) -> tuple[str, ...]:
        hashes = tuple(value.strip().lower() for value in (values or []) if value and value.strip())
        for value in hashes:
            if not _SHA256_HEX.fullmatch(value):
                raise ValueError("Service client key hashes must be hex SHA-256 digests (64 characters)")
        return hashes

    def accepts(self, key: str) -> bool:
        """Constant-time check of `key` against every configured hash."""
        candidate = hash_key(key)
        matches = [hmac.compare_digest(candidate, stored.get_secret_value()) for stored in self.key_hashes]
        return any(matches)
