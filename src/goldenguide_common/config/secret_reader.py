"""Port for reading configuration values and secrets.

Code depends on this Protocol rather than on os.environ, so the source can change (environment
variables locally, AWS Secrets Manager / Parameter Store in the cloud) without touching callers.
"""
from typing import Protocol, overload


class SecretReader(Protocol):
    # Overloads tell the type checker that passing a str default guarantees a str result.
    @overload
    def get(self, key: str, default: None = None) -> str | None: ...

    @overload
    def get(self, key: str, default: str) -> str: ...

    def get(self, key: str, default: str | None = None) -> str | None:
        """Return the value for `key`, or `default` if it is unset or empty."""
        ...
