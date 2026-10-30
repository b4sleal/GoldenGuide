"""Upsert update rules: what an incoming row does to an existing one (overwrite, keep on NULL,
flag re-embedding when embedded content changed).
"""
from collections.abc import Iterable, Mapping
from enum import StrEnum
from typing import Any

from sqlalchemy import case, func, or_, true
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.base import ReadOnlyColumnCollection
from sqlalchemy.sql.elements import ColumnElement

from backend.infra.persistence.db.dialects.ops import UpdateBuilder
from backend.infra.persistence.db.utils.generic.upsert_mapping import column_name


def overwrite(
        incoming: ReadOnlyColumnCollection,
        columns: Iterable[str],
) -> dict[str, ColumnElement[Any]]:
    return {name: incoming[name] for name in columns}


def preserve_on_null(
        existing: ReadOnlyColumnCollection,
        incoming: ReadOnlyColumnCollection,
        columns: Iterable[str],
) -> dict[str, ColumnElement[Any]]:
    return {
        name: func.coalesce(incoming[name], existing[name])
        for name in columns
    }


def reembed_on_change(
        existing: ReadOnlyColumnCollection,
        incoming: ReadOnlyColumnCollection,
        *,
        embed_fields: tuple[StrEnum, ...],
        flag_field: StrEnum,
        aliases: Mapping[str, InstrumentedAttribute],
) -> ColumnElement[Any]:
    """Set the flag when any embedded column changes; otherwise keep its stored value."""
    flag_name = column_name(flag_field.value, aliases)

    changes = [
        existing[column_name(field.value, aliases)].is_distinct_from(
            incoming[column_name(field.value, aliases)]
        )
        for field in embed_fields
    ]

    if not changes:
        return existing[flag_name]

    return case(
        (or_(*changes), true()),
        else_=existing[flag_name],
    )


def overwrite_and_flag_reembed(
        columns: Iterable[str],
        *,
        embed_fields: tuple[StrEnum, ...],
        flag_field: StrEnum,
        aliases: Mapping[str, InstrumentedAttribute],
) -> UpdateBuilder:
    """Upsert policy for embedded records: overwrite columns, but derive the re-embed flag from changes."""
    columns = tuple(columns)
    flag_name = column_name(flag_field.value, aliases)

    def build(existing: ReadOnlyColumnCollection, incoming: ReadOnlyColumnCollection) -> dict[str, ColumnElement[Any]]:
        updates = overwrite(incoming, columns)
        # The incoming flag is intentionally ignored: only an actual content change re-embeds.
        updates[flag_name] = reembed_on_change(
            existing,
            incoming,
            embed_fields=embed_fields,
            flag_field=flag_field,
            aliases=aliases,
        )
        return updates

    return build
