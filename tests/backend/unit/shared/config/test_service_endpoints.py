"""Real YAML layers preserve configured remote endpoints and local defaults."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from goldenguide_common.config.loader import ConfigLoader


class ConfigurationReader:
    def __init__(self, environment: str, **overrides: str) -> None:
        self.values = {
            "APP_ENV": environment,
            "CONFIG_PATH": str(Path(__file__).parents[5] / "configs"),
            "LOCAL_EMBEDDING_SERVICE__API_KEY": "test", "EMBEDDING_RUNTIME": "cpu",
            "BLOB_STORAGE__MINIO__ACCESS_KEY": "test", "BLOB_STORAGE__MINIO__SECRET_KEY": "test",
            "DB__POSTGRES__USER": "test", "DB__POSTGRES__PASSWORD": "test",
            "VECTOR_STORE__QDRANT__API_KEY": "test", "CACHE__REDIS__PASSWORD": "test",
            "MODEL_PROVIDER__GEMINI__API_KEY": "test", "MODEL_PROVIDER__OPENAI__API_KEY": "test",
        } | overrides

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
def test_remote_endpoints_survive_environment_layer(environment):
    config = ConfigLoader(ConfigurationReader(
        environment, DB__POSTGRES__HOST="db.internal", DB__POSTGRES__PORT="6543",
        VECTOR_STORE__QDRANT__HOST="vectors.internal", VECTOR_STORE__QDRANT__PORT="443",
        VECTOR_STORE__QDRANT__HTTPS="true", BLOB_STORAGE__MINIO__HOST="objects.internal",
        BLOB_STORAGE__MINIO__PORT="443", BLOB_STORAGE__MINIO__SECURE="true",
        CACHE__REDIS__HOST="state.internal", LOCAL_EMBEDDING_SERVICE__HOST="models.internal",
        LOCAL_EMBEDDING_SERVICE__PORT="8002",
    )).load_app_config()
    assert config.catalog.active.db["app"].host == "db.internal"
    assert config.catalog.active.db["app"].port == 6543
    assert config.catalog.active.vector_store["app"].host == "vectors.internal"
    assert config.catalog.active.vector_store["app"].https is True
    assert config.catalog.active.blob_storage["app"].host == "objects.internal"
    assert config.catalog.active.blob_storage["app"].secure is True
    assert config.catalog.active.cache["app"].host == "state.internal"
    assert config.local_embedding_service.host == "models.internal"
    assert config.local_embedding_service.port == 8002


def test_local_defaults_do_not_require_endpoint_variables():
    config = ConfigLoader(ConfigurationReader("development")).load_app_config()
    assert config.catalog.active.db["app"].host == "postgres"
    assert config.catalog.active.vector_store["app"].port == 6333
    assert config.catalog.active.cache["app"].host == "redis"


def test_endpoint_defaults_do_not_substitute_missing_credentials():
    reader = ConfigurationReader("development")
    del reader.values["DB__POSTGRES__PASSWORD"]
    with pytest.raises(ValidationError):
        ConfigLoader(reader).load_app_config()
