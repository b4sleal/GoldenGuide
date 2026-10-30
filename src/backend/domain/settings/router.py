"""Operational settings of the question router (catalogs/router/router.yml)."""
from pydantic import BaseModel, ConfigDict, Field


class FrozenRouterSettings(BaseModel):
    model_config = ConfigDict(frozen=True)


class EntityLookupCacheSettings(FrozenRouterSettings):
    """The cached list of known courses, subjects, programs, rooms and instructors."""
    ttl_seconds: int = Field(gt=0, description="How long a loaded lookup is reused before reloading.")
    batch_size: int = Field(gt=0, description="Rows per repository page while loading.")


class RouterSettings(FrozenRouterSettings):
    entity_lookup_cache: EntityLookupCacheSettings
