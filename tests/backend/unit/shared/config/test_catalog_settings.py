"""The real configs/ tree validates, including the institution and router catalogs the router needs."""
from pathlib import Path

from goldenguide_common.config.loader import ConfigLoader

CONFIG_ROOT = Path(__file__).parents[5] / "configs"


class PlaceholderSecrets:
    """Every secret resolves to a placeholder: this test checks structure, not credentials."""

    def get(self, key: str, default: str | None = None) -> str | None:
        known = {"APP_ENV": "development", "CONFIG_PATH": str(CONFIG_ROOT), "EMBEDDING_RUNTIME": "cpu"}
        if key.startswith("SERVICE_CLIENT__"):
            return None  # Unset, as by default: those clients are disabled (a placeholder is not a valid hash).
        return known.get(key, "1")


def test_institution_and_router_settings_load_from_yaml():
    catalog = ConfigLoader(PlaceholderSecrets()).load_app_config().catalog

    assert catalog.institution.code
    assert catalog.institution.zone.key == catalog.institution.timezone
    assert catalog.router.entity_lookup_cache.ttl_seconds > 0
    assert catalog.router.entity_lookup_cache.batch_size > 0
