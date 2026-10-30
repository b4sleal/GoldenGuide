"""Deterministic identifiers derived from content."""
import hashlib
import uuid


def sha256_hash(text: str) -> str:
    """Hex SHA-256 of `text`, used to detect whether content changed between scrapes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_uuid(text: str) -> str:
    """Stable UUIDv5 for `text`: the same content always maps to the same ID, so re-ingesting is idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, text))
