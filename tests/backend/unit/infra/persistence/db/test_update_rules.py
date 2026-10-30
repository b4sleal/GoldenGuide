"""The re-embed upsert policy, verified on the SET clauses it compiles to."""
from enum import StrEnum

from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

from backend.infra.persistence.db.utils.generic.update_rules import overwrite_and_flag_reembed


class PageField(StrEnum):
    TITLE = "title"
    BODY = "body"
    NEEDS_EMBEDDING = "needs_embedding"


PAGES = Table(
    "pages", MetaData(),
    Column("id", Integer, primary_key=True),
    Column("title", String),
    Column("body", String),
    Column("url", String),
    Column("needs_embedding", Boolean),
)


def compiled_updates(embed_fields, columns=("title", "body", "url", "needs_embedding")) -> dict[str, str]:
    excluded = insert(PAGES).excluded
    build = overwrite_and_flag_reembed(
        columns, embed_fields=embed_fields, flag_field=PageField.NEEDS_EMBEDDING, aliases={},
    )
    return {
        name: str(expression.compile(dialect=postgresql.dialect()))
        for name, expression in build(PAGES.c, excluded).items()
    }


def test_regular_columns_are_overwritten_from_the_incoming_row():
    updates = compiled_updates((PageField.TITLE, PageField.BODY))

    assert updates["title"] == "excluded.title"
    assert updates["url"] == "excluded.url"


def test_flag_is_raised_only_when_an_embedded_column_changes():
    flag = compiled_updates((PageField.TITLE, PageField.BODY))["needs_embedding"]

    assert "pages.title IS DISTINCT FROM excluded.title" in flag
    assert "pages.body IS DISTINCT FROM excluded.body" in flag
    assert "url" not in flag
    assert flag.endswith("ELSE pages.needs_embedding END")


def test_incoming_flag_value_never_overrides_change_detection():
    # needs_embedding is in the overwrite columns, yet the derived expression wins.
    flag = compiled_updates((PageField.TITLE,))["needs_embedding"]

    assert flag != "excluded.needs_embedding"
    assert flag.startswith("CASE")


def test_without_embedded_fields_the_stored_flag_is_kept():
    flag = compiled_updates(())["needs_embedding"]

    assert flag == "pages.needs_embedding"
