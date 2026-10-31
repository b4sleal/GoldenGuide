"""FastAPI dependencies for authenticating requests to the local model service."""

from secrets import compare_digest

from fastapi import Header, HTTPException


def build_api_key_verifier(expected_api_key: str):
    """Build a FastAPI dependency that validates the ``X-API-Key`` header.

    The comparison is constant-time, and missing or incorrect keys are rejected
    with the same ``401 Unauthorized`` response.
    """

    def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
        """Reject a request unless its API key matches the configured secret."""

        if not x_api_key or not compare_digest(x_api_key, expected_api_key):
            raise HTTPException(status_code=401, detail="Unauthorized")

    return verify_api_key