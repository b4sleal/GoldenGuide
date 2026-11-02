"""Request-size guard, so a misconfigured caller cannot exceed the limits the backend clients use."""

from fastapi import HTTPException, status


def build_text_limit(max_texts_per_request: int):
    """Build a check that rejects document requests above ``max_texts_per_request`` with ``413``."""

    def enforce_text_limit(texts: list[str]) -> None:
        """Raise ``413`` when a request carries more texts than one request may hold."""

        if len(texts) > max_texts_per_request:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"At most {max_texts_per_request} texts per request; got {len(texts)}",
            )

    return enforce_text_limit
