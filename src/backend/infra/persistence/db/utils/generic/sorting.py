"""Apply domain SortSpecs to a SELECT, always ending with a stable tie-breaker for deterministic paging."""
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from sqlalchemy import Select, inspect
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.ports.repositories.sorting import NullsPlacement, SortDirection, SortSpec

def apply_sorting[TOrder: StrEnum](
        stmt: Select,
        model: type,
        order_by: Sequence[SortSpec[TOrder]],
        aliases: dict[str, InstrumentedAttribute] | None = None,
        *,
        stable_tiebreaker: str = "id",
) -> Select:
    mapper = inspect(model)
    db_columns = mapper.columns

    if not order_by:
        tie_col = aliases[stable_tiebreaker] if aliases and stable_tiebreaker in aliases else db_columns.get(stable_tiebreaker)
        if tie_col is not None:
            return stmt.order_by(tie_col.asc())
        return stmt

    clauses: list[Any] = []

    for sort in order_by:
        string_key = sort.field.value

        if aliases and string_key in aliases:
            column = aliases[string_key]
        else:
            column = db_columns.get(string_key)
            if column is None:
                raise ValueError(f"Column '{string_key}' not found in database model.")

        clause = column.desc() if sort.direction == SortDirection.DESC else column.asc()

        if sort.nulls == NullsPlacement.FIRST:
            clause = clause.nulls_first()
        elif sort.nulls == NullsPlacement.LAST:
            clause = clause.nulls_last()

        clauses.append(clause)

    if stable_tiebreaker:
        tie_col = aliases[stable_tiebreaker] if aliases and stable_tiebreaker in aliases else db_columns.get(stable_tiebreaker)
        if tie_col is not None:
            clauses.append(tie_col.asc())

    return stmt.order_by(*clauses)