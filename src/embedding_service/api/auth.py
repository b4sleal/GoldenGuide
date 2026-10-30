from fastapi import Header, HTTPException
from secrets import compare_digest


def build_api_key_verifier(expected_api_key: str):
    def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if not x_api_key or not compare_digest(x_api_key, expected_api_key):
            raise HTTPException(status_code=401, detail="Unauthorized")

    return verify_api_key