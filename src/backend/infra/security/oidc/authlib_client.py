"""Provider-neutral OpenID Connect authorization-code client (PKCE S256, nonce-bound ID token).

Works with any standards-compliant provider (Keycloak locally; e.g. Microsoft Entra for WLU), because
everything is read from the provider's discovery document. Every ID token is verified before its
claims are trusted: signature against the provider's JWKS, issuer, audience/authorized party,
expiry and the login's nonce. Any failure raises; the login route turns that into a rejected login.

Network failures propagate as provider outages. Protocol/token rejections remain authentication
failures; neither path falls back to unverified claims. Logs never contain tokens or login secrets.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from backend.domain.entities.auth.oidc import ProviderMetadata
from backend.domain.settings.oidc import OIDCPolicy, OIDCSettings

# Uses the process-wide handlers and redaction configured by shared/logging.
logger = structlog.get_logger(__name__)


def _require_secure_url(url: str, name: str, local_development_hosts: set[str]) -> None:
    """HTTPS everywhere except the local development hosts configured in YAML."""
    parsed = urlparse(url)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_development_hosts):
        raise ValueError(f"OIDC {name} must use HTTPS outside local development")


class AuthlibOIDCClient:
    """Discover one provider and verify its ID tokens before exposing claims to the API."""

    def __init__(self, settings: OIDCSettings, policy: OIDCPolicy) -> None:
        self.settings = settings
        self.policy = policy
        self._metadata: ProviderMetadata | None = None

    async def initialize(self) -> None:
        """Read and validate the provider's discovery document (API startup)."""
        _require_secure_url(self.settings.discovery_url, "discovery", self.policy.local_development_hosts)

        async with httpx.AsyncClient(timeout=self.policy.http_timeout_seconds) as client:
            response = await client.get(self.settings.discovery_url)
            response.raise_for_status()
            metadata = response.json()

        required = tuple(ProviderMetadata.model_fields)
        if any(
                not isinstance(metadata.get(key), str) or not metadata[key]
                for key in required
        ):
            raise ValueError("Incomplete OIDC discovery metadata")

        provider = ProviderMetadata(
            **{key: metadata[key] for key in required}
        )

        for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            _require_secure_url(getattr(provider, name), name, self.policy.local_development_hosts)

        self._metadata = provider
        logger.info("oidc.discovery_initialized")

    @property
    def metadata(self) -> ProviderMetadata:
        """Prevent login requests from using an uninitialized provider."""
        if self._metadata is None:
            raise RuntimeError("OIDC discovery has not been initialized")
        return self._metadata

    def _client(self, state: str | None = None) -> AsyncOAuth2Client:
        """Create an OAuth client for one login attempt; no mutable state is shared across users."""
        return AsyncOAuth2Client(
            client_id=self.settings.client_id,
            # Public clients (PKCE only) have no secret.
            client_secret=self.settings.client_secret.get_secret_value() or None,
            redirect_uri=self.settings.redirect_uri,
            scope=self.settings.scope,
            state=state,
            code_challenge_method="S256",
            timeout=self.policy.http_timeout_seconds,
        )

    def authorization_url(
            self,
            *,
            state: str,
            verifier: str,
            nonce: str,
    ) -> str:
        """The provider login URL for one login attempt (state, PKCE verifier and nonce from the caller)."""
        client = self._client(state)

        url, returned_state = client.create_authorization_url(
            self.metadata.authorization_endpoint,
            state=state,
            code_verifier=verifier,
            nonce=nonce,
        )

        if returned_state != state:
            raise RuntimeError("OIDC authorization state mismatch")

        return url

    async def exchange(
            self,
            *,
            code: str,
            state: str,
            verifier: str,
            nonce: str,
    ) -> dict:
        """Exchange the callback code for tokens and return the verified ID token claims."""
        # Step 1: redeem the authorization code using the original PKCE verifier.
        async with self._client(state) as client:
            token = await client.fetch_token(
                self.metadata.token_endpoint,
                code=code,
                code_verifier=verifier,
                redirect_uri=self.settings.redirect_uri,
            )

        id_token = token.get("id_token")
        if not isinstance(id_token, str):
            # Keep ValueError: the API maps protocol rejection to 401 rather than a server error.
            raise ValueError("Identity provider did not return an ID token")  # noqa: TRY004

        # Step 2: fetch keys per login so rotated provider keys are always picked up.
        async with httpx.AsyncClient(timeout=self.policy.http_timeout_seconds) as client:
            response = await client.get(self.metadata.jwks_uri)
            response.raise_for_status()
            jwks = response.json()

        keys = KeySet.import_key_set(jwks)

        # Step 3: verify the signature before reading any claims, then validate required claims.
        verified = jwt.decode(
            id_token,
            keys,
            algorithms=self.policy.id_token_algorithms,
        )

        claims = verified.claims

        JWTClaimsRegistry(
            leeway=self.policy.clock_skew_seconds,
            iss={"essential": True, "value": self.metadata.issuer},
            aud={"essential": True},
            sub={"essential": True},
            exp={"essential": True},
            iat={"essential": True},
            nonce={"essential": True, "value": nonce},
        ).validate(claims)

        # The token must be issued to this client: our client_id among its audiences and, when several
        # audiences are present, as the authorized party (OIDC Core 3.1.3.7).
        audience = claims["aud"]
        audiences = [audience] if isinstance(audience, str) else audience

        if not isinstance(audiences, list) or self.settings.client_id not in audiences:
            raise ValueError("Invalid OIDC token audience")

        authorized_party = claims.get("azp")

        if len(audiences) > 1 and not authorized_party:
            raise ValueError("Missing OIDC authorized party")

        if authorized_party is not None and authorized_party != self.settings.client_id:
            raise ValueError("Invalid OIDC authorized party")

        # No subject, roles, code, state, nonce, verifier or token is included in this event.
        logger.debug("oidc.id_token_verified")
        return claims
