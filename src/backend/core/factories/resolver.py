"""Turn configuration catalogs ({name: settings}) into adapter instances via PROVIDER_REGISTRY.

Configuration mistakes fail at startup with a message naming the item and the valid choices, instead
of a bare KeyError or a silently replaced adapter.
"""
from backend.core.factories.registry import PROVIDER_REGISTRY
from backend.domain.common.providers_enum import PROVIDER_NAMESPACE


def resolve_catalog_items(catalog, provider_enum, **kwargs):
    """{name: adapter} for every item in `catalog`, built by the factory registered for its provider."""
    resolved = {}

    registry = PROVIDER_REGISTRY[PROVIDER_NAMESPACE[provider_enum]]

    for name, settings in catalog.items():
        provider = settings.provider
        factory = registry.get(provider)
        if factory is None:
            raise ValueError(
                f"Unknown provider '{provider}' for '{name}'. Registered: {sorted(str(key) for key in registry)}"
            )
        resolved[name] = factory(settings, **kwargs)

    return resolved


def merge_provider_maps(*maps):
    """Merge several {name: adapter} maps; a name defined twice is a configuration error."""
    merged = {}
    for m in maps:
        duplicates = merged.keys() & m.keys()
        if duplicates:
            raise ValueError(f"Provider names defined more than once: {sorted(duplicates)}")
        merged.update(m)
    return merged
