"""Logical key layout is shared by all byte-store implementations, not by Redis."""
from hashlib import sha256

class Keyspace:
    def __init__(self, namespace: str):
        self._namespace = namespace

    def record(self, identity: str) -> str:
        if not identity:
            raise ValueError("Identity must not be empty")
        digest = sha256(identity.encode("utf-8")).hexdigest()
        return f"gg:{self._namespace}:v1:{digest}"

    def singleton(self) -> str:
        return f"gg:{self._namespace}:v1"
