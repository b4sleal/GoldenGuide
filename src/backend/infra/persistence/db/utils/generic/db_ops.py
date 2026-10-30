"""Generic fetch (restricted to the view model's columns) and partial update for any table."""
from typing import Any
from pydantic import BaseModel
from sqlalchemy import Select, Update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import InstrumentedAttribute

from backend.domain.ports.repositories.pagination import PageParams
from backend.infra.persistence.db.utils.sql_updater import extract_payload
from backend.infra.persistence.db.utils.sql_view import apply_view

async def generic_fetch(
        session: AsyncSession,
        stmt: Select,
        db_model: type,
        view_model: type[BaseModel],
        page_params: PageParams,
        aliases: dict[str, InstrumentedAttribute] | None = None,
) -> list[Any]:
    stmt = apply_view(stmt, view_model, db_model, aliases)
    stmt = stmt.limit(page_params.limit).offset(page_params.offset)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    parsed_results = []
    for row in rows:
        row_dict = {}
        for domain_key in view_model.model_fields.keys():
            db_key = aliases[domain_key].key if aliases and domain_key in aliases else domain_key

            # Using __dict__ cleanly bypasses N+1 lazy-loading traps
            if db_key in row.__dict__:
                row_dict[domain_key] = row.__dict__[db_key]

        # from_attributes lets loaded child rows (ORM objects) validate into nested domain models.
        parsed_results.append(view_model.model_validate(row_dict, from_attributes=True))

    return parsed_results

async def generic_update(
        session: AsyncSession,
        stmt: Update,
        update_data: BaseModel,
        aliases: dict[str, InstrumentedAttribute] | None = None,
) -> int:
    safe_patch = extract_payload(update_data, aliases, exclude_unset=True)
    if not safe_patch:
        return 0

    result = await session.execute(
        stmt.values(**safe_patch)
    )

    return result.rowcount or 0
