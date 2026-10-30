"""OpenID Connect client settings (Keycloak locally; any standards-compliant provider in production)."""
from pydantic import BaseModel, ConfigDict, SecretStr


class OIDCPolicy(BaseModel):
    """OIDC transport and verification policy loaded from system.oidc in YAML."""

    model_config = ConfigDict(frozen=True)

    local_development_hosts: set[str]
    http_timeout_seconds: float
    clock_skew_seconds: int
    id_token_algorithms: list[str]


class OIDCSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    discovery_url: str
    client_id: str
    client_secret: SecretStr
    redirect_uri: str
    admin_role: str
    scope: str = "openid profile email"
