"""Prepare upsert rows: merge duplicate payloads per identity and map domain field names to columns."""
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table
from sqlalchemy.orm import InstrumentedAttribute, DeclarativeBase

from backend.infra.persistence.db.utils.sql_updater import extract_payload
from backend.shared.utils.frag_reducer import dedupe_fragments

def mapped_table(model: type[DeclarativeBase]) -> Table:
    table = model.__table__

    if not isinstance(table, Table):
        raise TypeError(f"{model.__name__} must map to a physical table.")

    return table

def column_name(
        field: str,
        aliases: Mapping[str, InstrumentedAttribute],
) -> str:
    column = aliases.get(field)
    return field if column is None else column.key


def prepare_rows(
        payloads: Sequence[BaseModel],
        *,
        identity_fields: Sequence[StrEnum],
        aliases: dict[str, InstrumentedAttribute],
) -> list[dict[str, Any]]:
    if not payloads:
        return []

    merged = dedupe_fragments(
        model_class=type(payloads[0]),
        fragments=list(payloads),
        fields=[field.value for field in identity_fields],
    )

    return [extract_payload(payload, aliases) for payload in merged]


def update_columns(
        update_model: type[BaseModel],
        *,
        identity_fields: Sequence[StrEnum],
        aliases: Mapping[str, InstrumentedAttribute],
) -> tuple[str, ...]:
    identity_columns = {
        column_name(field.value, aliases)
        for field in identity_fields
    }

    return tuple(
        column_name(field, aliases)
        for field in update_model.model_fields
        if column_name(field, aliases) not in identity_columns
    )