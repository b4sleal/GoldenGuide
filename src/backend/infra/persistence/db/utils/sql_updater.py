"""Domain payload -> column dict (respects unset/None exclusion and column aliases)."""
from typing import Any
from pydantic import BaseModel
from sqlalchemy.orm.attributes import InstrumentedAttribute


def extract_payload(
        payload: BaseModel | dict[str, Any],
        aliases: dict[str, InstrumentedAttribute] | None = None,
        *,
        exclude_unset: bool = False,
        exclude_none: bool = False,
) -> dict[str, Any]:
    """Dynamically extracts Pydantic payload and translates Domain keys to DB columns."""
    if isinstance(payload, BaseModel):
        data = payload.model_dump(exclude_unset=exclude_unset, exclude_none=exclude_none)
    else:
        data = { k: v for k, v in payload.items() if not (exclude_none and v is None) }

    if aliases:
        for domain_key, db_column in aliases.items():
            if domain_key in data:
                data[db_column.key] = data.pop(domain_key)
    return data