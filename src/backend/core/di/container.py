"""Root DI container. Configuration is loaded once at import (YAML layers + environment secrets);
sub-containers wire persistence, ML providers, services and startup steps from it.
"""
from dependency_injector import containers, providers

from backend.application.startup.app import AppStartup
from backend.core.di.wiring.ml import MLContainer
from backend.core.di.wiring.persistence import PersistenceContainer
from backend.core.di.wiring.services import ServiceContainer
from backend.core.di.wiring.startup import StartupContainer
from goldenguide_common.config.loader import ConfigLoader
from goldenguide_common.config.env_reader import EnvSecretReader
from goldenguide_common.logging.bootstrap import configure_observability

config = ConfigLoader(EnvSecretReader()).load_app_config()

class AppContainer(containers.DeclarativeContainer):
    secret_reader = providers.Singleton(EnvSecretReader)
    app_config = providers.Object(config)
    observability_startup = providers.Callable(
        configure_observability,
        reader=secret_reader,
    )

    wiring_config = containers.WiringConfiguration(
        packages=["backend.api", "backend.application"]
    )

    persistence = providers.Container(
        PersistenceContainer,
        catalog=app_config.provided.catalog
    )

    ml = providers.Container(
        MLContainer,
        catalog=app_config.provided.catalog,
        local_embedding_service=app_config.provided.local_embedding_service
    )

    startup = providers.Container(
        StartupContainer,
        catalog=app_config.provided.catalog,
        persistence=persistence,
    )

    services = providers.Container(
        ServiceContainer,
        persistence=persistence,
        ml=ml,
        catalog=app_config.provided.catalog,
        ai_behavior=app_config.provided.ai_behavior,
        jobs=app_config.provided.system.jobs,
    )

    # API replicas: read-only checks before serving traffic.
    startup_runner = providers.Singleton(AppStartup, initializers=startup.api_startup)

    # Provision job: create buckets/collections (after migrations). Never run by the API.
    provisioning_runner = providers.Singleton(AppStartup, initializers=startup.provisioning)
