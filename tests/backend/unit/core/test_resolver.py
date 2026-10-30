"""Provider resolution: configuration mistakes fail at startup with a readable message."""
from types import SimpleNamespace

import pytest

from backend.core.factories.resolver import merge_provider_maps, resolve_catalog_items
from backend.domain.common.providers_enum import CacheProvider


def test_unknown_provider_names_the_item_and_the_choices():
    catalog = {"app": SimpleNamespace(provider="memcached")}

    with pytest.raises(ValueError, match=r"Unknown provider 'memcached' for 'app'.*redis"):
        resolve_catalog_items(catalog, CacheProvider)


def test_duplicate_provider_names_are_rejected():
    with pytest.raises(ValueError, match="minilm"):
        merge_provider_maps({"minilm": object()}, {"minilm": object()})
