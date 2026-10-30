"""Provider-neutral discovery metadata needed for an OpenID Connect login."""
from pydantic import BaseModel, ConfigDict


class ProviderMetadata(BaseModel):
    """Provider identity and endpoints published by its discovery document."""

    model_config = ConfigDict(frozen=True)

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
