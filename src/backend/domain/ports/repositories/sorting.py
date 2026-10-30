"""Sort specifications shared by the repository query types."""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SortDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"

class NullsPlacement(StrEnum):
    FIRST = "first"
    LAST = "last"

class SortSpec[T: StrEnum](BaseModel):
    """
    Domain-level sorting instruction.

    `field` is not a database column.
    It is an approved semantic option for this repository.
    """
    model_config = ConfigDict(frozen=True)

    field: T
    direction: SortDirection = SortDirection.ASC
    nulls: NullsPlacement | None = None
