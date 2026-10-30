"""Configuration mistakes fail at boot: an unknown embedding runtime, an insecure OIDC endpoint."""
import pytest
from pydantic import ValidationError

from backend.domain.settings.ai_behavior import (
    AIBehaviorSettings,
    RuntimeDefaultsCatalog,
)
from goldenguide_common.contracts.embedding_models import LocalEmbeddingServiceSettings
from backend.infra.security.oidc.authlib_client import _require_secure_url

SERVICE = {"api_key": "k", "host": "embed", "port": 8001, "request_timeout_seconds": 5, "max_texts_per_request": 8}


def test_unknown_embedding_runtime_is_rejected():
    assert LocalEmbeddingServiceSettings(runtime="gpu", **SERVICE).runtime == "gpu"
    with pytest.raises(ValidationError):
        LocalEmbeddingServiceSettings(runtime="cuda", **SERVICE)  # Would otherwise load no models.


def test_oidc_requires_https_except_for_local_keycloak(oidc_policy):
    _require_secure_url("https://login.microsoftonline.com/x/v2.0/.well-known/openid-configuration", "discovery",
                        oidc_policy.local_development_hosts)
    _require_secure_url("http://keycloak:8080/realms/gg/.well-known/openid-configuration", "discovery",
                        oidc_policy.local_development_hosts)
    with pytest.raises(ValueError, match="HTTPS"):
        _require_secure_url("http://idp.example.com/.well-known/openid-configuration", "discovery",
                            oidc_policy.local_development_hosts)


def test_embedding_host_is_required_without_a_custom_validator():
    with pytest.raises(ValidationError, match="host"):
        LocalEmbeddingServiceSettings(runtime="cpu", **{key: value for key, value in SERVICE.items() if key != "host"})


@pytest.mark.parametrize("typed_defaults", [False, True])
def test_yaml_version_controls_defaults_without_modifying_input(typed_defaults):
    defaults = {"version": 2, "router_llm": {"prompt": "route"}, "generation_llm": {"prompt": "answer"}}
    original = RuntimeDefaultsCatalog(**defaults) if typed_defaults else defaults
    settings = AIBehaviorSettings(version=3, runtime_defaults=original, retrieval_strategy={})
    assert settings.runtime_defaults.version == 3
    assert settings.runtime_defaults.router_llm.prompt == "route"
    assert (original.version if typed_defaults else original["version"]) == 2
