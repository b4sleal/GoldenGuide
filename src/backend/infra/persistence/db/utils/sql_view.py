"""Restrict a SELECT to the columns a view model needs and eager-load its child collections."""
from pydantic import BaseModel
from sqlalchemy import Select, inspect
from sqlalchemy.orm import load_only, selectinload
from sqlalchemy.orm.attributes import InstrumentedAttribute

def apply_view(
        stmt: Select,
        view_model: type[BaseModel],
        db_model: type,
        aliases: dict[str, InstrumentedAttribute] | None = None,
) -> Select:
    """Dynamically restricts SELECT statements to only fetch requested Domain DTO columns,
    and eagerly loads the child collections the view asks for (one extra query each)."""
    mapper = inspect(db_model)
    sql_columns = []
    collections = []

    for field_name in view_model.model_fields.keys():
        if aliases and field_name in aliases:
            sql_columns.append(aliases[field_name])
        elif field_name in mapper.columns:
            sql_columns.append(getattr(db_model, field_name))
        elif field_name in mapper.relationships:
            collections.append(selectinload(getattr(db_model, field_name)))

    if sql_columns:
        stmt = stmt.options(load_only(*sql_columns))
    if collections:
        stmt = stmt.options(*collections)

    return stmt