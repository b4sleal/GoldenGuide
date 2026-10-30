"""Failure categories that any layer may raise and the API knows how to report.

Rule of thumb:
    - The code that detects a failure picks the category (it knows what went wrong).
    - The application decides whether to recover from it (retry, fallback, partial result).
    - The API maps whatever is left to an HTTP status / stream error event (api/errors.py).

Every error carries a `public_message` that is safe to show a student. Internal details
(SQL, hostnames, provider responses) belong in the exception chain (`raise ... from exc`),
which is logged server-side but never returned to the client.
"""


class GoldenGuideError(Exception):
    """Base class for anticipated failures. Raise a subclass, not this directly."""

    def __init__(self, public_message: str, *, internal_detail: str | None = None):
        # str(exc) is what logs show; prefer the internal detail when one is given.
        super().__init__(internal_detail or public_message)
        # Only this attribute is ever sent to clients.
        self.public_message = public_message


class InvalidInputError(GoldenGuideError):
    """The caller supplied something we cannot act on (bad settings update, unreadable file)."""


class NotFoundError(GoldenGuideError):
    """The requested record does not exist."""


class ConflictError(GoldenGuideError):
    """The request conflicts with current state (e.g. the same job is already running)."""


class DependencyUnavailableError(GoldenGuideError):
    """A required backing service (DB, Redis, Qdrant, LLM, embeddings) failed or is unreachable."""


class DeadlineExceededError(GoldenGuideError):
    """A required operation did not finish within its time budget."""
