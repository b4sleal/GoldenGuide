"""
Writes for aggregate roots whose payloads carry child collections.

A child collection is a one-to-many ORM relationship that owns its rows (cascade delete-orphan),
e.g. CourseTerm.meetings. Payload dicts carry it under the relationship's key as a list of
item dicts keyed by the child's ORM attribute names. Writing a collection replaces it whole:
the parent's current rows are deleted and the payload's items inserted in list order.
"""
from collections.abc import Mapping, Sequence
from itertools import batched
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, insert, inspect, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute, RelationshipProperty

from backend.domain.ports.repositories.types import PrimaryKey
from backend.infra.persistence.db.dialects.ops import SqlDialectOps, UpdateBuilder
from backend.infra.persistence.db.utils.generic.upsert_mapping import mapped_table
from backend.infra.persistence.db.utils.sql_updater import extract_payload

# Child collections are ordered lists; this column stores each item's index.
POSITION = "position"
# Keys per IN (...) clause, well under every supported driver's bind-parameter limit.
KEY_CHUNK = 1000

Children = dict[str, list[Mapping[str, Any]]]


def child_collections(model: type[DeclarativeBase]) -> dict[str, RelationshipProperty]:
    return {
        rel.key: rel
        for rel in inspect(model).relationships
        if rel.uselist and rel.cascade.delete_orphan
    }


def split_children(
        model: type[DeclarativeBase],
        rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[Children]]:
    """Separate column values from child collections. A None collection means "leave unchanged"."""
    collections = child_collections(model)
    parents: list[dict[str, Any]] = []
    children: list[Children] = []

    for row in rows:
        parent = dict(row)
        owned = {key: parent.pop(key) for key in collections if key in parent}
        parents.append(parent)
        children.append({key: items for key, items in owned.items() if items is not None})

    return parents, children


async def replace_children(
        session: AsyncSession,
        model: type[DeclarativeBase],
        parent_ids: Sequence[PrimaryKey],
        children: Sequence[Children],
) -> None:
    """For each parent, replace every collection present in its Children with those items."""
    for key, rel in child_collections(model).items():
        owners = [(parent_id, owned[key]) for parent_id, owned in zip(parent_ids, children) if key in owned]
        if not owners:
            continue

        child = rel.mapper
        foreign_key = _foreign_key_attribute(rel)
        writable = {attr.key for attr in child.column_attrs} - {foreign_key.key, POSITION}
        writable -= {column.key for column in child.primary_key}

        for chunk in batched([parent_id for parent_id, _ in owners], KEY_CHUNK):
            await session.execute(
                delete(child.class_).where(foreign_key.in_(chunk)),
                execution_options={"synchronize_session": False},
            )

        rows = [
            {**_child_values(item, writable, child.class_.__name__), foreign_key.key: parent_id, POSITION: index}
            for parent_id, items in owners
            for index, item in enumerate(items)
        ]
        if rows:
            await session.execute(insert(child.class_), rows)


async def upsert_aggregate(
        session: AsyncSession,
        dialect: SqlDialectOps,
        *,
        model: type[DeclarativeBase],
        rows: Sequence[Mapping[str, Any]],
        conflict_columns: Sequence[str],
        build_updates: UpdateBuilder,
) -> list[PrimaryKey]:
    """Upsert parent rows through the dialect, then replace the child collections they carry."""
    parents, children = split_children(model, rows)

    ids = await dialect.upsert(
        session,
        table=mapped_table(model),
        rows=parents,
        conflict_columns=conflict_columns,
        build_updates=build_updates,
    )

    if any(children):
        # RETURNING order is not guaranteed, so resolve each parent's id by its identity.
        owner_ids = await _ids_by_identity(session, model, conflict_columns, parents)
        await replace_children(session, model, owner_ids, children)

    return ids


async def update_aggregate(
        session: AsyncSession,
        model: type[DeclarativeBase],
        ids: Sequence[PrimaryKey],
        update_data: BaseModel,
        aliases: dict[str, InstrumentedAttribute],
) -> None:
    """PATCH semantics: set fields are written; set collections replace the stored ones."""
    patch = extract_payload(update_data, aliases, exclude_unset=True)
    [columns], [children] = split_children(model, [patch])
    primary_key = _single_primary_key(model)

    if columns:
        await session.execute(update(model).where(primary_key.in_(ids)).values(**columns))
    if children:
        await replace_children(session, model, ids, [children] * len(ids))


def _child_values(item: Mapping[str, Any], writable: set[str], child_name: str) -> dict[str, Any]:
    unknown = set(item) - writable
    if unknown:
        # A domain field with no column would otherwise be dropped silently.
        raise ValueError(f"{child_name} has no columns for {sorted(unknown)}")
    return {key: item.get(key) for key in writable}


def _foreign_key_attribute(rel: RelationshipProperty) -> InstrumentedAttribute:
    [(_, remote_column)] = rel.local_remote_pairs
    return getattr(rel.mapper.class_, rel.mapper.get_property_by_column(remote_column).key)


def _single_primary_key(model: type[DeclarativeBase]) -> InstrumentedAttribute:
    [column] = inspect(model).primary_key
    return getattr(model, inspect(model).get_property_by_column(column).key)


async def _ids_by_identity(
        session: AsyncSession,
        model: type[DeclarativeBase],
        identity_columns: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
) -> list[PrimaryKey]:
    table = mapped_table(model)
    identity = [table.c[name] for name in identity_columns]
    primary_key = _single_primary_key(model)
    keys = [tuple(row[name] for name in identity_columns) for row in rows]

    found: dict[tuple, PrimaryKey] = {}
    for chunk in batched(keys, KEY_CHUNK):
        result = await session.execute(
            select(primary_key, *identity).where(tuple_(*identity).in_(chunk))
        )
        found.update({tuple(row[1:]): row[0] for row in result.all()})

    return [found[key] for key in keys]
