"""Auth state kept in the session store: login sessions, in-flight OAuth logins, rate-limit decisions."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuthSession(BaseModel):
    """A logged-in user's session; invalid once `expires_at` has passed."""
    model_config = ConfigDict(frozen=True)

    subject: str
    roles: tuple[str, ...]
    expires_at: datetime


class OAuthTransaction(BaseModel):
    """State of one login between redirect and callback (PKCE verifier and nonce); single use."""
    model_config = ConfigDict(frozen=True)

    redirect_uri: str
    code_verifier: str
    nonce: str


class RateLimitDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    remaining: int
    retry_after_seconds: int
