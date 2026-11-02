"""The real configs/ tree validates, including the institution and router catalogs the router needs."""
from pathlib import Path

import yaml

from backend.domain.settings.jobs import JobExecutionMode
from goldenguide_common.config.loader import ConfigLoader

CONFIG_ROOT = Path(__file__).parents[5] / "configs"


class PlaceholderSecrets:
    """Every secret resolves to a placeholder: this test checks structure, not credentials."""

    def get(self, key: str, default: str | None = None) -> str | None:
        known = {"APP_ENV": "development", "CONFIG_PATH": str(CONFIG_ROOT), "EMBEDDING_RUNTIME": "cpu"}
        if key.startswith("SERVICE_CLIENT__"):
            return None  # Unset, as by default: those clients are disabled (a placeholder is not a valid hash).
        # Like EnvSecretReader: a config default (e.g. JOBS__EXECUTION -> in_process) wins over the placeholder.
        return known.get(key, default if default is not None else "1")


def test_institution_and_router_settings_load_from_yaml():
    catalog = ConfigLoader(PlaceholderSecrets()).load_app_config().catalog

    assert catalog.institution.code
    assert catalog.institution.zone.key == catalog.institution.timezone
    assert catalog.router.entity_lookup_cache.ttl_seconds > 0
    assert catalog.router.entity_lookup_cache.batch_size > 0


def test_jobs_run_in_process_unless_worker_execution_is_configured():
    jobs = ConfigLoader(PlaceholderSecrets()).load_app_config().system.jobs
    assert jobs.execution == JobExecutionMode.IN_PROCESS

    # Running jobs must be able to finish (or be recorded as interrupted) before Docker kills the worker.
    compose = yaml.safe_load((CONFIG_ROOT.parent / "docker-compose.yml").read_text(encoding="utf-8"))
    stop_grace = compose["services"]["worker"]["stop_grace_period"]
    assert stop_grace.endswith("s")
    assert jobs.worker.shutdown_graceful_timeout_seconds < float(stop_grace.removesuffix("s"))
