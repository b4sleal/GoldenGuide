"""Base paging parameters (limit, offset, ordering)."""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from backend.domain.ports.repositories.sorting import SortSpec


class PageParams[T: StrEnum](BaseModel):
    model_config = ConfigDict(frozen=True)

    """Universal pagination definition for all repository queries."""
    limit: int = Field(default=100, ge=1, le=10000)
    offset: int = Field(default=0, ge=0)
    order_by: list[SortSpec[T]] = Field(default_factory=list)
